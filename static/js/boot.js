// Runs before first paint (classic script in <head>): apply the saved language, theme and motion to <html>
// so the page never flashes the wrong theme. js/prefs.js owns these keys afterwards; keep the logic in sync.
(function () {
  var d = document.documentElement, get = function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } };
  var mq = function (q) { try { return matchMedia(q).matches; } catch (e) { return false; } };
  var lang = get('spk.lang'), theme = get('spk.theme'), motion = get('spk.motion');
  d.lang = lang === 'th' ? 'th' : 'en';
  d.dataset.theme = theme === 'light' || theme === 'dark' ? theme : (mq('(prefers-color-scheme: dark)') ? 'dark' : 'light');
  d.dataset.motion = motion === 'on' ? 'reduce' : motion === 'off' ? 'full' : (mq('(prefers-reduced-motion: reduce)') ? 'reduce' : 'full');
})();
// Behave like an app on phones: iOS Safari ignores maximum-scale for pinch, so cancel its pinch gestures here
// (scrolling and text selection are untouched; html/body set touch-action: manipulation against double-tap zoom).
['gesturestart', 'gesturechange', 'gestureend'].forEach(function (t) {
  document.addEventListener(t, function (e) { e.preventDefault(); }, { passive: false });
});
