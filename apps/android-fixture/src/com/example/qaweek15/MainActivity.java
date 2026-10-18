package com.example.qaweek15;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Bundle;
import android.view.ViewGroup;
import android.webkit.WebView;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class MainActivity extends Activity {
    private static final int CAMERA_REQUEST_CODE = 1501;

    private TextView statusView;
    private TextView resumeView;
    private int resumeCount;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        WebView.setWebContentsDebuggingEnabled(true);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(48, 72, 48, 48);

        TextView title = new TextView(this);
        title.setText("QA Week15 Fixture");
        title.setTextSize(24);
        root.addView(title);

        statusView = new TextView(this);
        statusView.setText("Ready");
        statusView.setContentDescription("fixture-status");
        statusView.setTextSize(18);
        statusView.setPadding(0, 36, 0, 36);
        root.addView(statusView);

        resumeView = new TextView(this);
        resumeView.setText("Resume count: 0");
        resumeView.setContentDescription("fixture-resume");
        resumeView.setTextSize(16);
        resumeView.setPadding(0, 0, 0, 24);
        root.addView(resumeView);

        Button requestCamera = new Button(this);
        requestCamera.setText("Request camera");
        requestCamera.setContentDescription("request-camera");
        requestCamera.setOnClickListener(new android.view.View.OnClickListener() {
            @Override
            public void onClick(android.view.View view) {
                requestPermissions(
                        new String[]{Manifest.permission.CAMERA},
                        CAMERA_REQUEST_CODE
                );
            }
        });
        root.addView(requestCamera);

        WebView webView = new WebView(this);
        webView.getSettings().setJavaScriptEnabled(true);
        webView.setContentDescription("fixture-webview");
        webView.loadDataWithBaseURL(
                "https://fixture.local/",
                "<html><body><h1 id=\"fixture-hybrid\">Hybrid ready</h1>"
                        + "<button id=\"fixture-web-button\">Web action</button></body></html>",
                "text/html",
                "UTF-8",
                null
        );
        root.addView(
                webView,
                new LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        900
                )
        );

        setContentView(
                root,
                new ViewGroup.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.MATCH_PARENT
                )
        );
        handleIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
    }

    @Override
    protected void onResume() {
        super.onResume();
        resumeCount += 1;
        resumeView.setText("Resume count: " + resumeCount);
    }

    @Override
    public void onRequestPermissionsResult(
            int requestCode,
            String[] permissions,
            int[] grantResults
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != CAMERA_REQUEST_CODE) {
            return;
        }
        boolean granted = grantResults.length > 0
                && grantResults[0] == PackageManager.PERMISSION_GRANTED;
        statusView.setText(granted ? "Camera granted" : "Camera denied");
        statusView.setContentDescription(
                granted ? "fixture-status:camera-granted" : "fixture-status:camera-denied"
        );
    }

    private void handleIntent(Intent intent) {
        Uri data = intent == null ? null : intent.getData();
        if (data == null) {
            return;
        }
        statusView.setText("Deep link: " + data);
        statusView.setContentDescription("fixture-status:deep-link:" + data);
    }
}
