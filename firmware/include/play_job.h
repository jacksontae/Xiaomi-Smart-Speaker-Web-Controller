// The steps of a `play` as a small state machine, so a cold start (launch the Default Media Receiver,
// wait for its transport, connect, LOAD) never blocks loop(). Pure logic: CastClient feeds it what it
// sees and performs the action it returns. Builds on the host for tests.
//
//   Volume (optional) -> Launch (skipped when the app already runs) -> WaitApp -> Load -> Done | Failed
#pragma once

#include <stdint.h>
#include <string.h>

namespace playjob {

// Per-step limits; together they stay under the server's 45 s timeout for `play`.
constexpr uint32_t kVolumeMs = 5000;
constexpr uint32_t kLaunchMs = 10000;   // for the LAUNCH reply
constexpr uint32_t kAppStartMs = 10000; // for the app's transportId after the reply
constexpr uint32_t kLoadMs = 15000;

enum class Phase : uint8_t { Idle, Volume, Launch, WaitApp, Load, Done, Failed };
enum class Action : uint8_t { None, SendVolume, SendLaunch, SendConnect, SendLoad, Succeed, Fail };
enum class Failure : uint8_t { None, LinkLost, Rejected, NoAnswer, AppDidNotStart, Cancelled };

// What the Cast client sees right now.
struct View {
    bool linkUp = true;
    bool appReady = false;            // Default Media Receiver runs and has a transportId
    bool transportConnected = false;  // CONNECT already sent to that transportId
    bool replied = false;             // the reply to our last request arrived
    bool replyRejected = false;       // ... and it was an error (LOAD_FAILED, LAUNCH_ERROR, ...)
};

// Reply types that mean the speaker refused a request.
inline bool isErrorReply(const char* type) {
    return !strcmp(type, "LOAD_FAILED") || !strcmp(type, "LOAD_CANCELLED") || !strcmp(type, "INVALID_REQUEST") ||
           !strcmp(type, "LAUNCH_ERROR");
}

class Job {
   public:
    void start(bool withVolume, uint32_t now) {
        failure_ = Failure::None;
        failedIn_ = Phase::Idle;
        enter(withVolume ? Phase::Volume : Phase::Launch, now);
    }

    bool active() const { return phase_ != Phase::Idle && phase_ != Phase::Done && phase_ != Phase::Failed; }
    Phase phase() const { return phase_; }
    Failure failure() const { return failure_; }
    Phase failedIn() const { return failedIn_; }  // which step failed, to name the request in the error

    // Ends an active job; the next step() reports Fail with Failure::Cancelled.
    void cancel() {
        if (active()) cancelled_ = true;
    }

    // Call on every loop; returns the one thing to do now. After a Send* the caller resets View::replied
    // for the new request. Send failures show up as linkUp = false on the next call.
    Action step(const View& v, uint32_t now) {
        if (!active()) return Action::None;
        if (cancelled_) return fail(Failure::Cancelled);
        if (!v.linkUp) return fail(Failure::LinkLost);
        switch (phase_) {
            case Phase::Volume:
                if (!waiting_) return send(Action::SendVolume, now);
                if (v.replied) {
                    if (v.replyRejected) return fail(Failure::Rejected);
                    enter(Phase::Launch, now);
                    return step(v, now);
                }
                return timedOut(now, kVolumeMs) ? fail(Failure::NoAnswer) : Action::None;
            case Phase::Launch:
                if (!waiting_ && v.appReady) {  // warm: the app already runs
                    enter(Phase::Load, now);
                    return step(v, now);
                }
                if (!waiting_) return send(Action::SendLaunch, now);
                if (v.replied) {
                    if (v.replyRejected) return fail(Failure::Rejected);
                    enter(Phase::WaitApp, now);  // the reply can come before the app is up
                    return step(v, now);
                }
                return timedOut(now, kLaunchMs) ? fail(Failure::NoAnswer) : Action::None;
            case Phase::WaitApp:
                if (v.appReady) {
                    enter(Phase::Load, now);
                    return step(v, now);
                }
                return timedOut(now, kAppStartMs) ? fail(Failure::AppDidNotStart) : Action::None;
            case Phase::Load:
                if (!waiting_) {
                    if (!v.transportConnected) return Action::SendConnect;  // no reply to wait for
                    return send(Action::SendLoad, now);
                }
                if (v.replied) {
                    if (v.replyRejected) return fail(Failure::Rejected);
                    phase_ = Phase::Done;
                    return Action::Succeed;
                }
                return timedOut(now, kLoadMs) ? fail(Failure::NoAnswer) : Action::None;
            default:
                return Action::None;
        }
    }

   private:
    void enter(Phase p, uint32_t now) {
        phase_ = p;
        since_ = now;
        waiting_ = false;
        cancelled_ = false;
    }
    Action send(Action a, uint32_t now) {
        waiting_ = true;
        since_ = now;
        return a;
    }
    Action fail(Failure f) {
        failure_ = f;
        failedIn_ = phase_;
        phase_ = Phase::Failed;
        cancelled_ = false;
        return Action::Fail;
    }
    bool timedOut(uint32_t now, uint32_t limit) const { return now - since_ >= limit; }  // wraps safely

    Phase phase_ = Phase::Idle;
    Phase failedIn_ = Phase::Idle;
    Failure failure_ = Failure::None;
    uint32_t since_ = 0;
    bool waiting_ = false;
    bool cancelled_ = false;
};

}  // namespace playjob
