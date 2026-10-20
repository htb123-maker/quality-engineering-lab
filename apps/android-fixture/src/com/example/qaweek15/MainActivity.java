package com.example.qaweek15;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.DialogInterface;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.ViewGroup;
import android.webkit.WebView;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

public final class MainActivity extends Activity {
    private static final int CAMERA_REQUEST_CODE = 1501;

    private TextView statusView;
    private TextView resumeView;
    private TextView formStatusView;
    private TextView counterView;
    private EditText inputView;
    private int resumeCount;
    private int counter;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        WebView.setWebContentsDebuggingEnabled(true);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(48, 72, 48, 48);

        TextView title = new TextView(this);
        title.setText("QA Android Fixture");
        title.setContentDescription("fixture-title");
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

        inputView = new EditText(this);
        inputView.setHint("Test input");
        inputView.setContentDescription("fixture-input");
        inputView.setInputType(InputType.TYPE_CLASS_TEXT);
        inputView.setSingleLine(true);
        root.addView(inputView);

        Button submit = new Button(this);
        submit.setText("Submit");
        submit.setContentDescription("fixture-submit");
        submit.setOnClickListener(new android.view.View.OnClickListener() {
            @Override
            public void onClick(android.view.View view) {
                String submitted = inputView.getText().toString();
                if (submitted.trim().isEmpty()) {
                    formStatusView.setText("Input required");
                    return;
                }
                formStatusView.setText("Submitted: " + submitted);
            }
        });
        root.addView(submit);

        Button reset = new Button(this);
        reset.setText("Reset");
        reset.setContentDescription("fixture-reset");
        reset.setOnClickListener(new android.view.View.OnClickListener() {
            @Override
            public void onClick(android.view.View view) {
                inputView.setText("");
                counter = 0;
                updateCounter();
                formStatusView.setText("Form idle");
            }
        });
        root.addView(reset);

        formStatusView = new TextView(this);
        formStatusView.setText("Form idle");
        formStatusView.setContentDescription("fixture-form-status");
        formStatusView.setTextSize(16);
        root.addView(formStatusView);

        counterView = new TextView(this);
        counterView.setTextSize(16);
        counterView.setContentDescription("fixture-counter-value");
        updateCounter();
        root.addView(counterView);

        Button increment = new Button(this);
        increment.setText("Increment");
        increment.setContentDescription("fixture-counter");
        increment.setOnClickListener(new android.view.View.OnClickListener() {
            @Override
            public void onClick(android.view.View view) {
                counter += 1;
                updateCounter();
            }
        });
        root.addView(increment);

        Button openDialog = new Button(this);
        openDialog.setText("Open dialog");
        openDialog.setContentDescription("fixture-modal");
        openDialog.setOnClickListener(new android.view.View.OnClickListener() {
            @Override
            public void onClick(android.view.View view) {
                new AlertDialog.Builder(MainActivity.this)
                        .setTitle("Fixture dialog")
                        .setMessage("Choose a dialog action")
                        .setPositiveButton(
                                "Confirm",
                                new DialogInterface.OnClickListener() {
                                    @Override
                                    public void onClick(DialogInterface dialog, int which) {
                                        formStatusView.setText("Dialog confirmed");
                                    }
                                }
                        )
                        .setNegativeButton(
                                "Cancel",
                                new DialogInterface.OnClickListener() {
                                    @Override
                                    public void onClick(DialogInterface dialog, int which) {
                                        formStatusView.setText("Dialog canceled");
                                    }
                                }
                        )
                        .show();
            }
        });
        root.addView(openDialog);

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
                        600
                )
        );

        ScrollView scroll = new ScrollView(this);
        scroll.addView(root);
        setContentView(scroll);
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

    private void updateCounter() {
        counterView.setText("Counter: " + counter);
    }
}
