package com.krazow.webapp;

import android.Manifest;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.util.Base64;
import android.webkit.GeolocationPermissions;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.ServiceWorkerClient;
import android.webkit.ServiceWorkerController;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.webkit.WebViewAssetLoader;
import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewFeature;

import java.io.OutputStream;
import java.util.Collections;

/**
 * Krazow release kit: the shared Android wrapper. The app's web files are packed in the APK and shown in a
 * full-screen web view at https://appassets.androidplatform.net/www/ (a secure origin, so storage, location and
 * the service worker behave as in a browser). Works offline from the first launch.
 * Downloads made by the page (an <a download> link to a blob: or data: address) are saved with Android's
 * "Save to" screen.
 */
public class MainActivity extends Activity {
    private static final String HOST = "appassets.androidplatform.net";
    private static final String HOME = "https://" + HOST + "/www/index.html";
    private static final int REQ_FILE = 1, REQ_SAVE = 2, REQ_LOCATION = 3;

    // Turns <a download href="blob:..."> clicks into a call to the Android bridge.
    private static final String DOWNLOAD_SHIM =
        "(function(){if(window.__kitDl)return;window.__kitDl=1;" +
        "document.addEventListener('click',function(e){var a=e.target&&e.target.closest&&e.target.closest('a[download]');" +
        "if(!a||!/^(blob|data):/.test(a.href))return;e.preventDefault();e.stopImmediatePropagation();" +
        "fetch(a.href).then(function(r){return r.blob()}).then(function(b){var f=new FileReader();f.onload=function(){" +
        "KrazowAndroid.saveFile('dl'+Date.now(),a.getAttribute('download')||'download',b.type||'',String(f.result).split(',')[1]||'')};" +
        "f.readAsDataURL(b)})},true)})();";

    private WebView web;
    private WebViewAssetLoader assets;
    private ValueCallback<Uri[]> fileCallback;
    private GeolocationPermissions.Callback geoCallback;
    private String geoOrigin;
    private String saveId;
    private byte[] saveBytes;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        assets = new WebViewAssetLoader.Builder().setDomain(HOST).addPathHandler("/", new WebViewAssetLoader.AssetsPathHandler(this)).build();
        web = new WebView(this);
        web.setFitsSystemWindows(true);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setGeolocationEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(true);
        s.setSupportMultipleWindows(false);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setUserAgentString(s.getUserAgentString() + " KrazowAndroid/" + versionName());

        if (WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
            WebViewCompat.addDocumentStartJavaScript(web, DOWNLOAD_SHIM, Collections.singleton("https://" + HOST));
        }
        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest req) {
                return serve(req.getUrl());
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                if (HOST.equals(u.getHost())) return false;
                openOutside(u);
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                if (!WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) view.evaluateJavascript(DOWNLOAD_SHIM, null);
            }
        });
        if (Build.VERSION.SDK_INT >= 24) {
            ServiceWorkerController.getInstance().setServiceWorkerClient(new ServiceWorkerClient() {
                @Override
                public WebResourceResponse shouldInterceptRequest(WebResourceRequest req) {
                    return serve(req.getUrl());
                }
            });
        }
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onGeolocationPermissionsShowPrompt(String origin, GeolocationPermissions.Callback callback) {
                if (hasLocation()) { callback.invoke(origin, true, true); return; }
                geoOrigin = origin;
                geoCallback = callback;
                requestPermissions(new String[] { Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION }, REQ_LOCATION);
            }

            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent pick = params.createIntent();
                if (params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE) pick.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                String[] types = params.getAcceptTypes();
                boolean images = types != null && types.length > 0;
                if (images) for (String t : types) if (!t.startsWith("image/")) images = false;
                if (!images) pick.setType("*/*");
                try {
                    startActivityForResult(Intent.createChooser(pick, null), REQ_FILE);
                } catch (ActivityNotFoundException e) {
                    fileCallback = null;
                    return false;
                }
                return true;
            }

            @Override
            public void onPermissionRequest(PermissionRequest request) {
                request.deny(); // no live camera or microphone; photos come through the file picker
            }
        });
        web.addJavascriptInterface(new Bridge(), "KrazowAndroid");

        if (state != null) web.restoreState(state);
        else web.loadUrl(HOME);
    }

    // App files from the APK; a folder address ("/www/") gets its index.html, as on a web server.
    private WebResourceResponse serve(Uri u) {
        if (HOST.equals(u.getHost()) && u.getPath() != null && u.getPath().endsWith("/")) u = u.buildUpon().path(u.getPath() + "index.html").build();
        return assets.shouldInterceptRequest(u);
    }

    private boolean hasLocation() {
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
            || checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    private void openOutside(Uri u) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, u));
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this, "No app can open that link", Toast.LENGTH_SHORT).show();
        }
    }

    private String versionName() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "?";
        }
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] results) {
        if (code == REQ_LOCATION && geoCallback != null) {
            geoCallback.invoke(geoOrigin, hasLocation(), true);
            geoCallback = null;
        }
    }

    @Override
    protected void onActivityResult(int code, int result, Intent data) {
        if (code == REQ_FILE && fileCallback != null) {
            Uri[] picked = null;
            if (result == RESULT_OK && data != null) {
                ClipData clip = data.getClipData();
                if (clip != null) {
                    picked = new Uri[clip.getItemCount()];
                    for (int i = 0; i < clip.getItemCount(); i++) picked[i] = clip.getItemAt(i).getUri();
                } else if (data.getData() != null) {
                    picked = new Uri[] { data.getData() };
                }
            }
            fileCallback.onReceiveValue(picked);
            fileCallback = null;
        } else if (code == REQ_SAVE) {
            boolean ok = false;
            if (result == RESULT_OK && data != null && data.getData() != null && saveBytes != null) {
                try (OutputStream out = getContentResolver().openOutputStream(data.getData(), "wt")) {
                    out.write(saveBytes);
                    ok = true;
                } catch (Exception e) {
                    Toast.makeText(this, "Couldn't save the file", Toast.LENGTH_LONG).show();
                }
            }
            if (ok) Toast.makeText(this, "Saved", Toast.LENGTH_SHORT).show();
            String id = saveId;
            saveId = null;
            saveBytes = null;
            if (id != null) web.evaluateJavascript("window.__androidSaved && window.__androidSaved('" + id.replaceAll("[^A-Za-z0-9]", "") + "'," + ok + ")", null);
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onPause() {
        super.onPause();
        web.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
    }

    /** window.KrazowAndroid in the page. */
    private class Bridge {
        @JavascriptInterface
        public void saveFile(String id, String name, String mime, String base64) {
            runOnUiThread(() -> {
                try {
                    saveBytes = Base64.decode(base64, Base64.DEFAULT);
                    saveId = id;
                    Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                    i.addCategory(Intent.CATEGORY_OPENABLE);
                    i.setType(mime == null || mime.isEmpty() ? "application/octet-stream" : mime);
                    i.putExtra(Intent.EXTRA_TITLE, name);
                    startActivityForResult(i, REQ_SAVE);
                } catch (Exception e) {
                    saveBytes = null;
                    saveId = null;
                    Toast.makeText(MainActivity.this, "Couldn't save the file", Toast.LENGTH_LONG).show();
                }
            });
        }

        @JavascriptInterface
        public String version() {
            return versionName();
        }

        @JavascriptInterface
        public String platform() {
            return "android " + Build.VERSION.RELEASE;
        }
    }
}
