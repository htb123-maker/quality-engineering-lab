package com.example.qaweek15;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.LocaleManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.LocaleList;
import android.text.InputType;
import android.text.TextUtils;
import android.util.Base64;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebView;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int CAMERA_REQUEST_CODE = 1501;
    private static final int NOTIFICATION_REQUEST_CODE = 1502;
    private static final int NOTIFICATION_ID = 1502;
    private static final String NOTIFICATION_CHANNEL_ID = "qa-week15-status";

    private TextView statusView;
    private TextView resumeView;
    private TextView formStatusView;
    private TextView counterView;
    private TextView catalogStatusView;
    private TextView catalogItemView;
    private Button catalogArchiveButton;
    private EditText inputView;
    private String catalogBaseUrl = "";
    private String catalogSessionId = "";
    private int resumeCount;
    private int counter;
    private final ExecutorService catalogExecutor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        applySystemTheme();
        super.onCreate(savedInstanceState);
        WebView.setWebContentsDebuggingEnabled(true);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(48, 72, 48, 48);
        root.setLayoutDirection(
                isRtl() ? View.LAYOUT_DIRECTION_RTL : View.LAYOUT_DIRECTION_LTR
        );

        TextView title = textDirection(new TextView(this));
        title.setText(t("QA Android Fixture", "QA Android 测试夹具", "جسر اختبار Android"));
        title.setContentDescription("fixture-title");
        title.setTextSize(24);
        root.addView(title);

        statusView = textDirection(new TextView(this));
        statusView.setText(t("Ready", "就绪", "جاهز"));
        statusView.setContentDescription("fixture-status");
        statusView.setTextSize(18);
        statusView.setPadding(0, 36, 0, 36);
        root.addView(statusView);

        catalogStatusView = textDirection(new TextView(this));
        catalogStatusView.setText("catalog: idle");
        catalogStatusView.setContentDescription("catalog-status");
        catalogStatusView.setTextSize(16);
        root.addView(catalogStatusView);

        catalogItemView = textDirection(new TextView(this));
        catalogItemView.setText("catalog item: none");
        catalogItemView.setContentDescription("catalog-item");
        catalogItemView.setTextSize(16);
        root.addView(catalogItemView);

        Button refreshCatalog = textDirection(new Button(this));
        refreshCatalog.setText("Refresh catalog");
        refreshCatalog.setContentDescription("catalog-refresh");
        refreshCatalog.setOnClickListener(new android.view.View.OnClickListener() {
            @Override
            public void onClick(android.view.View view) {
                requestCatalog(false);
            }
        });
        root.addView(refreshCatalog);

        catalogArchiveButton = textDirection(new Button(this));
        catalogArchiveButton.setText("Archive catalog item");
        catalogArchiveButton.setContentDescription("catalog-archive");
        catalogArchiveButton.setEnabled(false);
        catalogArchiveButton.setOnClickListener(new android.view.View.OnClickListener() {
            @Override
            public void onClick(android.view.View view) {
                requestCatalog(true);
            }
        });
        root.addView(catalogArchiveButton);

        resumeView = textDirection(new TextView(this));
        resumeView.setText(t("Resume count: 0", "恢复次数：0", "عدد الاستئناف: 0"));
        resumeView.setContentDescription("fixture-resume");
        resumeView.setTextSize(16);
        resumeView.setPadding(0, 0, 0, 24);
        root.addView(resumeView);

        Button requestCamera = textDirection(new Button(this));
        requestCamera.setText(t("Request camera", "请求相机权限", "طلب إذن الكاميرا"));
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

        Button postNotification = textDirection(new Button(this));
        postNotification.setText(t("Post notification", "发送通知", "إرسال إشعار"));
        postNotification.setContentDescription("post-notification");
        postNotification.setOnClickListener(new android.view.View.OnClickListener() {
            @Override
            public void onClick(android.view.View view) {
                requestOrPostNotification();
            }
        });
        root.addView(postNotification);

        inputView = textDirection(new EditText(this));
        inputView.setHint(t("Test input", "测试输入", "إدخال اختبار"));
        inputView.setContentDescription("fixture-input");
        inputView.setInputType(InputType.TYPE_CLASS_TEXT);
        inputView.setSingleLine(true);
        root.addView(inputView);

        Button submit = textDirection(new Button(this));
        submit.setText(t("Submit", "提交", "إرسال"));
        submit.setContentDescription("fixture-submit");
        submit.setOnClickListener(new android.view.View.OnClickListener() {
            @Override
            public void onClick(android.view.View view) {
                String submitted = inputView.getText().toString();
                if (submitted.trim().isEmpty()) {
                    formStatusView.setText(
                            t("Input required", "请输入内容", "الإدخال مطلوب")
                    );
                    return;
                }
                formStatusView.setText(t("Submitted: ", "已提交：", "تم الإرسال: ") + submitted);
            }
        });
        root.addView(submit);

        Button reset = textDirection(new Button(this));
        reset.setText(t("Reset", "重置", "إعادة تعيين"));
        reset.setContentDescription("fixture-reset");
        reset.setOnClickListener(new android.view.View.OnClickListener() {
            @Override
            public void onClick(android.view.View view) {
                inputView.setText("");
                counter = 0;
                updateCounter();
                formStatusView.setText(t("Form idle", "表单空闲", "النموذج خامل"));
            }
        });
        root.addView(reset);

        formStatusView = textDirection(new TextView(this));
        formStatusView.setText(t("Form idle", "表单空闲", "النموذج خامل"));
        formStatusView.setContentDescription("fixture-form-status");
        formStatusView.setTextSize(16);
        root.addView(formStatusView);

        counterView = textDirection(new TextView(this));
        counterView.setTextSize(16);
        counterView.setContentDescription("fixture-counter-value");
        updateCounter();
        root.addView(counterView);

        Button increment = textDirection(new Button(this));
        increment.setText(t("Increment", "增加", "زيادة"));
        increment.setContentDescription("fixture-counter");
        increment.setOnClickListener(new android.view.View.OnClickListener() {
            @Override
            public void onClick(android.view.View view) {
                counter += 1;
                updateCounter();
            }
        });
        root.addView(increment);

        Button openDialog = textDirection(new Button(this));
        openDialog.setText(t("Open dialog", "打开对话框", "فتح الحوار"));
        openDialog.setContentDescription("fixture-modal");
        openDialog.setOnClickListener(new android.view.View.OnClickListener() {
            @Override
            public void onClick(android.view.View view) {
                new AlertDialog.Builder(MainActivity.this)
                        .setTitle(t("Fixture dialog", "测试对话框", "حوار الاختبار"))
                        .setMessage(
                                t(
                                        "Choose a dialog action",
                                        "选择对话框操作",
                                        "اختر إجراءً للحوار"
                                )
                        )
                        .setPositiveButton(
                                t("Confirm", "确认", "تأكيد"),
                                new DialogInterface.OnClickListener() {
                                    @Override
                                    public void onClick(DialogInterface dialog, int which) {
                                        formStatusView.setText(
                                                t(
                                                        "Dialog confirmed",
                                                        "对话框已确认",
                                                        "تم تأكيد الحوار"
                                                )
                                        );
                                    }
                                }
                        )
                        .setNegativeButton(
                                t("Cancel", "取消", "إلغاء"),
                                new DialogInterface.OnClickListener() {
                                    @Override
                                    public void onClick(DialogInterface dialog, int which) {
                                        formStatusView.setText(
                                                t(
                                                        "Dialog canceled",
                                                        "对话框已取消",
                                                        "تم إلغاء الحوار"
                                                )
                                        );
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
        webView.setLayoutDirection(
                isRtl() ? View.LAYOUT_DIRECTION_RTL : View.LAYOUT_DIRECTION_LTR
        );
        String webDirection = isRtl() ? "rtl" : "ltr";
        String webHeading = t("Hybrid ready", "混合页已就绪", "الواجهة الهجينة جاهزة");
        String webAction = t("Web action", "网页操作", "إجراء الويب");
        webView.loadDataWithBaseURL(
                "https://fixture.local/",
                "<html><head><style>"
                        + "body{background:#fff;color:#000;font-family:sans-serif}"
                        + "@media (prefers-color-scheme:dark){"
                        + "body{background:#121212;color:#f5f5f5}}"
                        + "</style></head><body dir=\"" + webDirection + "\">"
                        + "<h1 id=\"fixture-hybrid\">" + webHeading + "</h1>"
                        + "<button id=\"fixture-web-button\">" + webAction + "</button>"
                        + "</body></html>",
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

    private void applySystemTheme() {
        int nightMode = getResources().getConfiguration().uiMode
                & Configuration.UI_MODE_NIGHT_MASK;
        setTheme(
                nightMode == Configuration.UI_MODE_NIGHT_YES
                        ? android.R.style.Theme_Material_NoActionBar
                        : android.R.style.Theme_Material_Light_NoActionBar
        );
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
        resumeView.setText(t("Resume count: ", "恢复次数：", "عدد الاستئناف: ") + resumeCount);
    }

    @Override
    protected void onDestroy() {
        catalogExecutor.shutdownNow();
        super.onDestroy();
    }

    @Override
    public void onRequestPermissionsResult(
            int requestCode,
            String[] permissions,
            int[] grantResults
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        boolean granted = grantResults.length > 0
                && grantResults[0] == PackageManager.PERMISSION_GRANTED;
        if (requestCode == NOTIFICATION_REQUEST_CODE) {
            if (granted) {
                postNotification();
            } else {
                statusView.setText(t("Notification denied", "通知权限已拒绝", "تم رفض الإشعار"));
                statusView.setContentDescription("fixture-status:notification-denied");
            }
            return;
        }
        if (requestCode != CAMERA_REQUEST_CODE) {
            return;
        }
        statusView.setText(
                granted
                        ? t("Camera granted", "相机权限已允许", "تم منح إذن الكاميرا")
                        : t("Camera denied", "相机权限已拒绝", "تم رفض إذن الكاميرا")
        );
        statusView.setContentDescription(
                granted ? "fixture-status:camera-granted" : "fixture-status:camera-denied"
        );
    }

    private Locale appLocale() {
        if (Build.VERSION.SDK_INT >= 33) {
            LocaleManager localeManager = getSystemService(LocaleManager.class);
            LocaleList applicationLocales = localeManager.getApplicationLocales();
            if (!applicationLocales.isEmpty()) {
                return applicationLocales.get(0);
            }
        }
        Configuration configuration = getResources().getConfiguration();
        return configuration.getLocales().isEmpty()
                ? Locale.getDefault()
                : configuration.getLocales().get(0);
    }

    private boolean isRtl() {
        return TextUtils.getLayoutDirectionFromLocale(appLocale())
                == View.LAYOUT_DIRECTION_RTL;
    }

    private String t(String english, String chinese, String arabic) {
        String language = appLocale().getLanguage();
        if ("zh".equals(language)) {
            return chinese;
        }
        if ("ar".equals(language)) {
            return arabic;
        }
        return english;
    }

    private <T extends TextView> T textDirection(T view) {
        view.setTextDirection(View.TEXT_DIRECTION_LOCALE);
        return view;
    }

    private void handleIntent(Intent intent) {
        Uri data = intent == null ? null : intent.getData();
        if (data == null) {
            return;
        }
        if ("e2e".equals(data.getHost())) {
            String baseUrl = null;
            String sessionId = null;
            if (!data.getPathSegments().isEmpty()) {
                try {
                    byte[] decoded = Base64.decode(
                            data.getPathSegments().get(0),
                            Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING
                    );
                    JSONObject payload = new JSONObject(
                            new String(decoded, StandardCharsets.UTF_8)
                    );
                    baseUrl = payload.getString("e2eBaseUrl");
                    sessionId = payload.getString("sessionId");
                } catch (Exception ignored) {
                    baseUrl = null;
                    sessionId = null;
                }
            }
            if (baseUrl != null && !baseUrl.isEmpty()
                    && sessionId != null && !sessionId.isEmpty()) {
                catalogBaseUrl = baseUrl;
                catalogSessionId = sessionId;
                catalogArchiveButton.setEnabled(false);
                requestCatalog(false);
                return;
            }
        }
        statusView.setText(t("Deep link: ", "深链接：", "رابط عميق: ") + data);
        statusView.setContentDescription("fixture-status:deep-link:" + data);
    }

    private void requestCatalog(boolean archive) {
        if (catalogBaseUrl.isEmpty() || catalogSessionId.isEmpty()) {
            catalogStatusView.setText("catalog: error|missing-session");
            return;
        }
        catalogStatusView.setText("catalog: loading");
        catalogArchiveButton.setEnabled(false);
        catalogExecutor.execute(new Runnable() {
            @Override
            public void run() {
                HttpURLConnection connection = null;
                try {
                    String suffix = "/api/v1/e2e/sessions/"
                            + URLEncoder.encode(catalogSessionId, "UTF-8")
                            + (archive ? "/archive" : "");
                    URL url = new URL(catalogBaseUrl.replaceAll("/+$", "") + suffix);
                    connection = (HttpURLConnection) url.openConnection();
                    connection.setConnectTimeout(5000);
                    connection.setReadTimeout(5000);
                    connection.setRequestMethod(archive ? "POST" : "GET");
                    int statusCode = connection.getResponseCode();
                    if (statusCode < 200 || statusCode >= 300) {
                        throw new IllegalStateException("HTTP " + statusCode);
                    }
                    String body;
                    try (BufferedReader reader = new BufferedReader(
                            new InputStreamReader(
                                    connection.getInputStream(),
                                    StandardCharsets.UTF_8
                            )
                    )) {
                        StringBuilder builder = new StringBuilder();
                        String line;
                        while ((line = reader.readLine()) != null) {
                            builder.append(line);
                        }
                        body = builder.toString();
                    }
                    JSONObject item = new JSONObject(body);
                    String itemStatus = item.getString("status");
                    String itemName = item.getString("name");
                    int itemId = item.getInt("id");
                    mainHandler.post(new Runnable() {
                        @Override
                        public void run() {
                            catalogStatusView.setText(
                                    "catalog: " + itemStatus + "|" + itemId + "|" + itemName
                            );
                            catalogItemView.setText("catalog item: " + itemName);
                            catalogArchiveButton.setEnabled("active".equals(itemStatus));
                        }
                    });
                } catch (Exception error) {
                    mainHandler.post(new Runnable() {
                        @Override
                        public void run() {
                            catalogStatusView.setText(
                                    "catalog: error|" + error.getClass().getSimpleName()
                            );
                        }
                    });
                } finally {
                    if (connection != null) {
                        connection.disconnect();
                    }
                }
            }
        });
    }

    private void requestOrPostNotification() {
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(
                    new String[]{Manifest.permission.POST_NOTIFICATIONS},
                    NOTIFICATION_REQUEST_CODE
            );
            return;
        }
        postNotification();
    }

    private void postNotification() {
        NotificationManager manager = getSystemService(NotificationManager.class);
        NotificationChannel channel = new NotificationChannel(
                NOTIFICATION_CHANNEL_ID,
                "QA fixture status",
                NotificationManager.IMPORTANCE_DEFAULT
        );
        channel.setDescription("Controlled notifications for Android UI testing");
        manager.createNotificationChannel(channel);

        Intent launchIntent = new Intent(this, MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent contentIntent = PendingIntent.getActivity(
                this,
                0,
                launchIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        Notification notification = new Notification.Builder(this, NOTIFICATION_CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle(
                        t(
                                "QA Week15 notification",
                                "QA Week15 通知",
                                "إشعار QA Week15"
                        )
                )
                .setContentText(
                        t(
                                "Notification channel is ready",
                                "通知渠道已就绪",
                                "قناة الإشعارات جاهزة"
                        )
                )
                .setContentIntent(contentIntent)
                .setAutoCancel(true)
                .setOnlyAlertOnce(true)
                .setCategory(Notification.CATEGORY_STATUS)
                .build();
        manager.notify(NOTIFICATION_ID, notification);
        statusView.setText(t("Notification posted", "通知已发送", "تم إرسال الإشعار"));
        statusView.setContentDescription("fixture-status:notification-posted");
    }

    private void updateCounter() {
        counterView.setText(t("Counter: ", "计数器：", "العداد: ") + counter);
    }
}
