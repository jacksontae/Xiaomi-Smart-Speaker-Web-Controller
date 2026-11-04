// Host tests for the non-blocking play state machine: `pio test -e native`
#include <unity.h>

#include "play_job.h"

using playjob::Action;
using playjob::Failure;
using playjob::Job;
using playjob::Phase;
using playjob::View;

void setUp() {}
void tearDown() {}

static View warm() {
    View v;
    v.appReady = true;
    v.transportConnected = true;
    return v;
}

static View replied(View v, bool rejected = false) {
    v.replied = true;
    v.replyRejected = rejected;
    return v;
}

static void test_idle_job_does_nothing() {
    Job job;
    TEST_ASSERT_FALSE(job.active());
    TEST_ASSERT_EQUAL(Action::None, job.step(View{}, 0));
}

static void test_warm_play_goes_straight_to_load() {
    Job job;
    job.start(false, 0);
    TEST_ASSERT_EQUAL(Action::SendLoad, job.step(warm(), 0));
    TEST_ASSERT_EQUAL(Action::None, job.step(warm(), 10));  // waiting for the reply
    TEST_ASSERT_EQUAL(Action::Succeed, job.step(replied(warm()), 20));
    TEST_ASSERT_EQUAL(Phase::Done, job.phase());
    TEST_ASSERT_FALSE(job.active());
    TEST_ASSERT_EQUAL(Action::None, job.step(replied(warm()), 30));
}

static void test_warm_play_connects_transport_first_when_needed() {
    Job job;
    job.start(false, 0);
    View v = warm();
    v.transportConnected = false;
    TEST_ASSERT_EQUAL(Action::SendConnect, job.step(v, 0));
    v.transportConnected = true;
    TEST_ASSERT_EQUAL(Action::SendLoad, job.step(v, 0));
}

static void test_cold_play_launches_waits_connects_and_loads() {
    Job job;
    job.start(false, 0);
    View v;  // no app running
    TEST_ASSERT_EQUAL(Action::SendLaunch, job.step(v, 0));
    TEST_ASSERT_EQUAL(Action::None, job.step(v, 500));
    // LAUNCH answered, but the receiver status doesn't list the app yet
    TEST_ASSERT_EQUAL(Action::None, job.step(replied(v), 800));
    TEST_ASSERT_EQUAL(Phase::WaitApp, job.phase());
    TEST_ASSERT_EQUAL(Action::None, job.step(v, 2000));
    v.appReady = true;
    TEST_ASSERT_EQUAL(Action::SendConnect, job.step(v, 3000));
    v.transportConnected = true;
    TEST_ASSERT_EQUAL(Action::SendLoad, job.step(v, 3000));
    TEST_ASSERT_EQUAL(Action::Succeed, job.step(replied(v), 3500));
}

static void test_launch_reply_with_app_already_up_skips_waiting() {
    Job job;
    job.start(false, 0);
    View v;
    TEST_ASSERT_EQUAL(Action::SendLaunch, job.step(v, 0));
    v.appReady = true;
    TEST_ASSERT_EQUAL(Action::SendConnect, job.step(replied(v), 100));
}

static void test_volume_step_runs_first() {
    Job job;
    job.start(true, 0);
    TEST_ASSERT_EQUAL(Action::SendVolume, job.step(warm(), 0));
    TEST_ASSERT_EQUAL(Action::None, job.step(warm(), 50));
    TEST_ASSERT_EQUAL(Action::SendLoad, job.step(replied(warm()), 100));
}

static void test_rejected_reply_fails_and_names_the_step() {
    Job job;
    job.start(false, 0);
    TEST_ASSERT_EQUAL(Action::SendLaunch, job.step(View{}, 0));
    TEST_ASSERT_EQUAL(Action::Fail, job.step(replied(View{}, true), 10));
    TEST_ASSERT_EQUAL(Failure::Rejected, job.failure());
    TEST_ASSERT_EQUAL(Phase::Launch, job.failedIn());
    TEST_ASSERT_FALSE(job.active());
}

static void test_load_rejected() {
    Job job;
    job.start(false, 0);
    job.step(warm(), 0);
    TEST_ASSERT_EQUAL(Action::Fail, job.step(replied(warm(), true), 10));
    TEST_ASSERT_EQUAL(Phase::Load, job.failedIn());
}

static void test_launch_without_answer_times_out() {
    Job job;
    job.start(false, 0);
    job.step(View{}, 0);
    TEST_ASSERT_EQUAL(Action::None, job.step(View{}, playjob::kLaunchMs - 1));
    TEST_ASSERT_EQUAL(Action::Fail, job.step(View{}, playjob::kLaunchMs));
    TEST_ASSERT_EQUAL(Failure::NoAnswer, job.failure());
}

static void test_app_that_never_starts_times_out() {
    Job job;
    job.start(false, 0);
    job.step(View{}, 0);
    job.step(replied(View{}), 1000);  // WaitApp from t=1000
    TEST_ASSERT_EQUAL(Action::None, job.step(View{}, 1000 + playjob::kAppStartMs - 1));
    TEST_ASSERT_EQUAL(Action::Fail, job.step(View{}, 1000 + playjob::kAppStartMs));
    TEST_ASSERT_EQUAL(Failure::AppDidNotStart, job.failure());
}

static void test_load_timeout_counts_from_the_load_request() {
    Job job;
    job.start(false, 0);
    job.step(View{}, 0);
    View v = replied(View{});
    v.appReady = true;
    v.transportConnected = true;
    TEST_ASSERT_EQUAL(Action::SendLoad, job.step(v, 9000));
    TEST_ASSERT_EQUAL(Action::None, job.step(warm(), 9000 + playjob::kLoadMs - 1));
    TEST_ASSERT_EQUAL(Action::Fail, job.step(warm(), 9000 + playjob::kLoadMs));
    TEST_ASSERT_EQUAL(Phase::Load, job.failedIn());
}

static void test_timeouts_survive_millis_wraparound() {
    Job job;
    const uint32_t start = 0xFFFFFF00u;
    job.start(false, start);
    job.step(warm(), start);
    TEST_ASSERT_EQUAL(Action::None, job.step(warm(), start + 1000));  // wrapped past zero
    TEST_ASSERT_EQUAL(Action::Fail, job.step(warm(), start + playjob::kLoadMs));
}

static void test_lost_link_fails() {
    Job job;
    job.start(false, 0);
    job.step(View{}, 0);
    View v;
    v.linkUp = false;
    TEST_ASSERT_EQUAL(Action::Fail, job.step(v, 10));
    TEST_ASSERT_EQUAL(Failure::LinkLost, job.failure());
}

static void test_cancel() {
    Job job;
    job.cancel();  // nothing to cancel
    TEST_ASSERT_FALSE(job.active());
    job.start(false, 0);
    job.step(View{}, 0);
    job.cancel();
    TEST_ASSERT_EQUAL(Action::Fail, job.step(View{}, 10));
    TEST_ASSERT_EQUAL(Failure::Cancelled, job.failure());
    // a new job starts clean
    job.start(false, 20);
    TEST_ASSERT_EQUAL(Action::SendLoad, job.step(warm(), 20));
    TEST_ASSERT_EQUAL(Failure::None, job.failure());
}

static void test_error_reply_types() {
    TEST_ASSERT_TRUE(playjob::isErrorReply("LOAD_FAILED"));
    TEST_ASSERT_TRUE(playjob::isErrorReply("LOAD_CANCELLED"));
    TEST_ASSERT_TRUE(playjob::isErrorReply("INVALID_REQUEST"));
    TEST_ASSERT_TRUE(playjob::isErrorReply("LAUNCH_ERROR"));
    TEST_ASSERT_FALSE(playjob::isErrorReply("MEDIA_STATUS"));
    TEST_ASSERT_FALSE(playjob::isErrorReply("RECEIVER_STATUS"));
    TEST_ASSERT_FALSE(playjob::isErrorReply(""));
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_idle_job_does_nothing);
    RUN_TEST(test_warm_play_goes_straight_to_load);
    RUN_TEST(test_warm_play_connects_transport_first_when_needed);
    RUN_TEST(test_cold_play_launches_waits_connects_and_loads);
    RUN_TEST(test_launch_reply_with_app_already_up_skips_waiting);
    RUN_TEST(test_volume_step_runs_first);
    RUN_TEST(test_rejected_reply_fails_and_names_the_step);
    RUN_TEST(test_load_rejected);
    RUN_TEST(test_launch_without_answer_times_out);
    RUN_TEST(test_app_that_never_starts_times_out);
    RUN_TEST(test_load_timeout_counts_from_the_load_request);
    RUN_TEST(test_timeouts_survive_millis_wraparound);
    RUN_TEST(test_lost_link_fails);
    RUN_TEST(test_cancel);
    RUN_TEST(test_error_reply_types);
    return UNITY_END();
}
