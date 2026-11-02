// Runs before first paint (classic script in <head>): apply the saved language, theme and motion, and the OS look
// (data-os), to <html> so the page never flashes the wrong theme. js/prefs.js owns these keys afterwards; keep the logic in sync.
(function () {
  var d = document.documentElement, get = function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } };
  var mq = function (q) { try { return matchMedia(q).matches; } catch (e) { return false; } };
  var lang = get('spk.lang'), theme = get('spk.theme'), motion = get('spk.motion');
  d.lang = lang === 'th' ? 'th' : 'en';
  d.dataset.theme = theme === 'light' || theme === 'dark' ? theme : (mq('(prefers-color-scheme: dark)') ? 'dark' : 'light');
  d.dataset.motion = motion === 'on' ? 'reduce' : motion === 'off' ? 'full' : (mq('(prefers-reduced-motion: reduce)') ? 'reduce' : 'full');
  // The look follows the OS: Android phones and tablets get the Android look (Material/One UI, css/android.css);
  // everything else keeps the iPhone/iPad/desktop look. Keep in sync with prefs.js isAndroid().
  var ua = navigator.userAgentData && navigator.userAgentData.platform;
  var android = ua === 'Android' || /Android/i.test(navigator.userAgent);
  if (android) {
    d.dataset.os = 'android';
    // only Android devices download it; render-blocking so the first paint is already Material (no flash of glass)
    var l = document.createElement('link');
    l.rel = 'stylesheet'; l.id = 'android-css'; l.setAttribute('blocking', 'render');
    l.href = new URL('../css/android.css', document.currentScript.src).href;
    document.head.appendChild(l);
  }
})();
// Behave like an app on phones: iOS Safari ignores maximum-scale for pinch, so cancel its pinch gestures here
// (scrolling and text selection are untouched; html/body set touch-action: manipulation against double-tap zoom).
['gesturestart', 'gesturechange', 'gestureend'].forEach(function (t) {
  document.addEventListener(t, function (e) { e.preventDefault(); }, { passive: false });
});
