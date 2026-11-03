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
import android.os.LocaleList;
import android.text.InputType;
import android.text.TextUtils;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebView;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.Locale;

public final class MainActivity extends Activity {
    private static final int CAMERA_REQUEST_CODE = 1501;
    private static final int NOTIFICATION_REQUEST_CODE = 1502;
    private static final int NOTIFICATION_ID = 1502;
    private static final String NOTIFICATION_CHANNEL_ID = "qa-week15-status";

    private TextView statusView;
    private TextView resumeView;
    private TextView formStatusView;
    private TextView counterView;
    private EditText inputView;
    private int resumeCount;
    private int counter;

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
        statusView.setText(t("Deep link: ", "深链接：", "رابط عميق: ") + data);
        statusView.setContentDescription("fixture-status:deep-link:" + data);
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
