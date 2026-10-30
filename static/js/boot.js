// Runs before first paint (classic script in <head>): apply the saved language, theme, motion and look (data-os) to <html>
// so the page never flashes the wrong theme. js/prefs.js owns these keys afterwards; keep the logic in sync.
(function () {
  var d = document.documentElement, get = function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } };
  var mq = function (q) { try { return matchMedia(q).matches; } catch (e) { return false; } };
  var lang = get('spk.lang'), theme = get('spk.theme'), motion = get('spk.motion');
  d.lang = lang === 'th' ? 'th' : 'en';
  d.dataset.theme = theme === 'light' || theme === 'dark' ? theme : (mq('(prefers-color-scheme: dark)') ? 'dark' : 'light');
  d.dataset.motion = motion === 'on' ? 'reduce' : motion === 'off' ? 'full' : (mq('(prefers-reduced-motion: reduce)') ? 'reduce' : 'full');
  // Look: Android (Material/One UI, css/android.css) or the default glass look. ?os=android|ios|auto saves a choice
  // (spk.os, also in App settings) and drops the parameter from the address; 'auto' follows the device.
  var m = /[?&]os=(android|ios|auto)\b/.exec(location.search);
  if (m) {
    try { localStorage.setItem('spk.os', m[1]); } catch (e) { /* applies to this page only */ }
    try { history.replaceState(history.state, '', location.pathname + location.search.replace(/([?&])os=[^&]*&?/, '$1').replace(/[?&]$/, '') + location.hash); } catch (e) { /* keep the address */ }
  }
  var os = (m && m[1]) || get('spk.os');
  var ua = navigator.userAgentData && navigator.userAgentData.platform;
  var android = os === 'android' || (os !== 'ios' && (ua === 'Android' || /Android/i.test(navigator.userAgent)));
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
