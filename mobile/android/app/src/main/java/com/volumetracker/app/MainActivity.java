package com.volumetracker.app;

import android.content.ContentValues;
import android.content.res.Configuration;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.view.View;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import android.widget.Toast;
import androidx.activity.OnBackPressedCallback;
import androidx.annotation.NonNull;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.WebViewListener;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;

/**
 * 볼륨 트래커 웹 화면(서버가 내려 주는 React 앱)을 감싸는 액티비티.
 * 화면과 기능은 전부 웹 쪽에 있고, 여기서는 브라우저와 달라서 안드로이드 앱에서만 필요한 일을 처리한다:
 * 상태바 여백, 상태바 색, 뒤로가기, 파일 내려받기.
 */
public class MainActivity extends BridgeActivity {

    /**
     * 웹 화면이 뜰 때마다 넣는 스크립트. 웹 코드는 고치지 않고 앱 쪽에서만 두 가지를 보탠다.
     *
     * 1) 화면의 배경색과 다크 여부를 알려 준다. 테마가 바뀌면(html 의 class) 다시 알린다.
     *    웹 화면은 시스템과 다른 테마를 직접 고를 수 있어서, 시스템 테마가 아니라 실제 화면을 기준으로 삼는다.
     * 2) 내려받기를 앱으로 넘긴다. 웹 화면은 받은 데이터를 blob 주소로 만들어 a[download].click() 으로
     *    내려받는데(CSV 내보내기), 웹뷰는 이 방식의 내려받기를 처리하지 않아 아무 일도 일어나지 않는다.
     */
    private static final String PAGE_HOOKS_JS =
        """
        (function () {
          if (!window.VTAndroid) return;

          function reportColors() {
            var bg = getComputedStyle(document.body).backgroundColor;
            var m = /rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/.exec(bg);
            if (!m) return;
            var hex = '#' + [m[1], m[2], m[3]].map(function (n) { return ('0' + Number(n).toString(16)).slice(-2); }).join('');
            window.VTAndroid.pageColors(hex, document.documentElement.classList.contains('dark'));
          }
          if (!window.__vtReportBars) {
            new MutationObserver(reportColors).observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
          }
          window.__vtReportBars = reportColors;
          reportColors();

          if (!window.__vtDownloadHook) {
            window.__vtDownloadHook = true;
            var browserClick = HTMLAnchorElement.prototype.click;
            HTMLAnchorElement.prototype.click = function () {
              var a = this;
              if (!a.hasAttribute('download') || a.href.indexOf('blob:') !== 0) return browserClick.apply(a, arguments);
              var name = a.download || 'download';
              // 웹 코드는 click() 직후에 blob 주소를 지운다. 그 전에 여기서 읽기 시작해야 한다.
              fetch(a.href)
                .then(function (res) { return res.blob(); })
                .then(function (blob) {
                  var reader = new FileReader();
                  reader.onload = function () {
                    window.VTAndroid.saveFile(name, blob.type || 'application/octet-stream', String(reader.result).split(',')[1] || '');
                  };
                  reader.readAsDataURL(blob);
                })
                .catch(function () { window.VTAndroid.saveFailed(name); });
            };
          }
        })();
        """;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        keepContentClearOfSystemBars();
        connectPageToApp();
        goBackInsideTheWebApp();
    }

    @Override
    public void onConfigurationChanged(@NonNull Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        // 시스템 테마가 바뀌면 Capacitor 가 상태바 색을 시스템 기준으로 되돌린다. 화면 기준으로 다시 맞춘다.
        if (getBridge() != null && getBridge().getWebView() != null) {
            getBridge().getWebView().evaluateJavascript(PAGE_HOOKS_JS, null);
        }
    }

    /**
     * 상태바·내비게이션 바·키보드만큼 안쪽으로 여백을 준다.
     * 웹 화면은 브라우저 기준으로 만들어져 위쪽 안전 영역을 비워 두지 않는다. 여백 없이 두면
     * 화면 맨 위 내용이 상태바 밑으로 들어간다(안드로이드 15+는 앱을 화면 끝까지 그린다).
     * 여백 처리를 한 곳에서만 하도록 capacitor.config.js 에서 SystemBars.insetsHandling 을 꺼 두었다.
     */
    private void keepContentClearOfSystemBars() {
        View content = findViewById(android.R.id.content);
        ViewCompat.setOnApplyWindowInsetsListener(content, (view, insets) -> {
            Insets bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout());
            Insets keyboard = insets.getInsets(WindowInsetsCompat.Type.ime());
            view.setPadding(bars.left, bars.top, bars.right, Math.max(bars.bottom, keyboard.bottom));
            // 여백으로 이미 반영했으므로 웹뷰에는 0으로 넘긴다(그대로 넘기면 웹뷰가 한 번 더 줄어든다)
            return new WindowInsetsCompat.Builder(insets)
                .setInsets(WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout(), Insets.NONE)
                .setInsets(WindowInsetsCompat.Type.ime(), Insets.NONE)
                .build();
        });
    }

    /** 웹 화면이 앱을 부를 창구(window.VTAndroid)를 열고, 화면이 뜰 때마다 PAGE_HOOKS_JS 를 넣는다. */
    private void connectPageToApp() {
        WebView webView = getBridge().getWebView();
        webView.addJavascriptInterface(new PageBridge(), "VTAndroid");
        getBridge().addWebViewListener(
            new WebViewListener() {
                @Override
                public void onPageLoaded(WebView view) {
                    view.evaluateJavascript(PAGE_HOOKS_JS, null);
                }
            }
        );
    }

    /** 웹 화면에서 부르는 메서드. 웹뷰의 별도 스레드에서 불리므로 화면을 건드릴 때는 UI 스레드로 넘긴다. */
    private class PageBridge {

        /** 상태바·내비게이션 바 뒤 여백의 색과 상태바 아이콘 색을 웹 화면의 현재 테마에 맞춘다. */
        @JavascriptInterface
        public void pageColors(String backgroundHex, boolean dark) {
            final int color;
            try {
                color = Color.parseColor(backgroundHex);
            } catch (IllegalArgumentException e) {
                return;
            }
            runOnUiThread(() -> {
                getWindow().getDecorView().setBackgroundColor(color);
                WindowInsetsControllerCompat bars = WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView());
                bars.setAppearanceLightStatusBars(!dark);
                bars.setAppearanceLightNavigationBars(!dark);
            });
        }

        /** 웹 화면이 내려받으려던 파일을 기기의 다운로드 폴더에 저장한다. */
        @JavascriptInterface
        public void saveFile(String name, String mimeType, String base64) {
            String fileName = new File(name).getName(); // 경로가 섞여 와도 파일 이름만 쓴다
            try {
                String where = writeToDownloads(fileName, mimeType, Base64.decode(base64, Base64.DEFAULT));
                toast(where + "에 저장했습니다: " + fileName);
            } catch (IOException | RuntimeException e) {
                saveFailed(fileName);
            }
        }

        @JavascriptInterface
        public void saveFailed(String name) {
            toast("저장하지 못했습니다: " + name);
        }
    }

    /** @return 저장한 곳의 이름(안내 문구용) */
    private String writeToDownloads(String fileName, String mimeType, byte[] data) throws IOException {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ContentValues values = new ContentValues();
            values.put(MediaStore.Downloads.DISPLAY_NAME, fileName);
            values.put(MediaStore.Downloads.MIME_TYPE, mimeType);
            Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
            if (uri == null) throw new IOException("MediaStore insert failed");
            try (OutputStream out = getContentResolver().openOutputStream(uri)) {
                if (out == null) throw new IOException("openOutputStream failed");
                out.write(data);
            }
            return "다운로드 폴더";
        }
        // 안드로이드 9 이하: 공용 다운로드 폴더는 저장 권한이 필요하다. 권한 없이 쓸 수 있는 앱 전용 폴더에 둔다.
        File dir = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
        if (dir == null) throw new IOException("no external files dir");
        try (OutputStream out = new FileOutputStream(new File(dir, fileName))) {
            out.write(data);
        }
        return "앱 폴더(Android/data/" + getPackageName() + "/files/Download)";
    }

    private void toast(String message) {
        runOnUiThread(() -> Toast.makeText(this, message, Toast.LENGTH_LONG).show());
    }

    /** 뒤로가기: 웹 화면 안에서 이전 화면으로 가고, 더 갈 곳이 없으면 앱을 닫지 않고 뒤로 보낸다. */
    private void goBackInsideTheWebApp() {
        getOnBackPressedDispatcher().addCallback(
            this,
            new OnBackPressedCallback(true) {
                @Override
                public void handleOnBackPressed() {
                    WebView webView = getBridge().getWebView();
                    if (webView.canGoBack()) {
                        webView.goBack();
                    } else {
                        moveTaskToBack(true);
                    }
                }
            }
        );
    }
}
