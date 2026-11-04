package org.onegram;

import android.app.Activity;
import android.content.*;
import android.net.Uri;
import android.os.*;
import android.util.Log;
import java.lang.reflect.*;
import java.lang.ref.WeakReference;
import java.util.regex.*;

public final class OneGramBoot {
    private static final Pattern LINKS = Pattern.compile("https?://\\S+|tg://\\S+|@[A-Za-z0-9_]+");
    private static int generation;
    private static final Handler HANDLER = new Handler(Looper.getMainLooper());

    public static void start(Activity activity) {
        OneGramUi.rememberActivity(activity);
        if(!OneGramConfig.proxyEnabled())return;
        try {
            Intent service = new Intent(activity, OneGramService.class);
            service.setAction(OneGramService.ACTION_RESUME);
            if (Build.VERSION.SDK_INT >= 26) activity.startForegroundService(service);
            else activity.startService(service);
        } catch (RuntimeException e) {
            Log.e("OneGram", "Cannot start connection service", e);
        }
    }

    public static void resume(Activity activity) {
        start(activity);
        int token = ++generation;
        WeakReference<Activity> reference = new WeakReference<>(activity);
        HANDLER.postDelayed(new Runnable(){public void run(){
            Activity current=reference.get();if(token!=generation||current==null||current.isFinishing()||current.isDestroyed())return;
            try{org.onegram.streak.StreakUi.updateProgress(current.getWindow().getDecorView());}catch(Exception ignored){}
            HANDLER.postDelayed(this,1000);
        }},1000);

        HANDLER.postDelayed(new Runnable() {
            public void run() {
                Activity current = reference.get();
                if (token != generation || current == null || current.isFinishing() || current.isDestroyed()) return;
                try {
                    Class<?> config = Class.forName("org.telegram.messenger.UserConfig");
                    int selected = config.getField("selectedAccount").getInt(null);
                    Object account = config.getMethod("getInstance", int.class).invoke(null, selected);
                    boolean active = (Boolean) config.getMethod("isClientActivated").invoke(account);
                    long id = active ? ((Number) config.getMethod("getClientUserId").invoke(account)).longValue() : 0;
                    SharedPreferences prefs=current.getSharedPreferences("onegram",Context.MODE_PRIVATE);
                    String opened="channel_opened_account_"+id;
                    String joined="channel_joined_account_"+id;
                    if(id>0&&current.hasWindowFocus()){
                        ChannelSubscription.ensure(current,selected,id);
                        if(!prefs.getBoolean(opened,false)){
                            OneGramUi.openUpdates(current);
                            prefs.edit().putBoolean(opened,true).commit();
                        }
                    }
                    if(id>0&&prefs.getBoolean(opened,false)&&prefs.getBoolean(joined,false))return;

                } catch (Exception e) { Log.w("OneGram", "Waiting to open the channel after login", e); }
                if (token == generation) HANDLER.postDelayed(this, 1200);
            }
        }, 700);
    }

    public static void pause(Activity activity) { generation++; }

    public static String brand(String value) {
        if (value == null) return null;
        if (value.equals("https://t.me/TelegramTips")) return "https://t.me/On3Gram";
        if (!value.contains("OneGram") && !value.contains("ONEGRAM") && !value.contains("Telegram") && !value.contains("TELEGRAM") && !value.contains("РўРµР»РµРіСЂР°Рј") && !value.contains("С‚РµР»РµРіСЂР°Рј")) return value;
        Matcher matcher = LINKS.matcher(value);
        StringBuilder result = new StringBuilder();
        int offset = 0;
        while (matcher.find()) {
            result.append(label(value.substring(offset, matcher.start())));
            result.append(matcher.group());
            offset = matcher.end();
        }
        return result.append(label(value.substring(offset))).toString();
    }

    private static String label(String text) {
        return BrandingLabels.plain(text);
    }

    static void configureProxy(Context context,int port,String secret)throws Exception {
        configureProxy(context,port,secret,OneGramConfig.proxyEnabled());
    }
    static void disableProxy(Context context)throws Exception {
        SharedPreferences prefs=context.getSharedPreferences("onegram",Context.MODE_PRIVATE);
        String secret=prefs.getString("proxy_secret","");int port=prefs.getInt("proxy_port",0);
        if(secret.length()==32&&port>0)configureProxy(context,port,secret,false);
        else context.getSharedPreferences("mainconfig",Context.MODE_PRIVATE).edit().putBoolean("proxy_enabled",false).commit();
    }
    static void configureProxy(Context context, int port, String secret,boolean enabled) throws Exception {
        Class<?> loader = Class.forName("org.telegram.messenger.ApplicationLoader");
        loader.getMethod("postInitApplication").invoke(null);
        SharedPreferences prefs = context.getSharedPreferences("mainconfig", Context.MODE_PRIVATE);
        prefs.edit().putBoolean("proxy_enabled", enabled).putBoolean("proxy_enabled_calls", false)
            .putString("proxy_ip", "127.0.0.1").putInt("proxy_port", port).putInt("proxy_type", 1)
            .putString("proxy_user", "").putString("proxy_pass", "").putString("proxy_secret", "dd" + secret).commit();
        Class<?> connections = Class.forName("org.telegram.tgnet.ConnectionsManager");
        Class<?> shared = Class.forName("org.telegram.messenger.SharedConfig");
        try {
            Method method = connections.getMethod("setProxySettings", boolean.class, String.class, int.class,
                String.class, String.class, String.class);
            Object info = shared.getMethod("addProxy", String.class, int.class, String.class, String.class, String.class)
                .invoke(null, "127.0.0.1", port, "", "", "dd" + secret);
            shared.getField("currentProxy").set(null, info);
            method.invoke(null, enabled, "127.0.0.1", port, "", "", "dd" + secret);
        } catch (NoSuchMethodException e) {
            Method setter = null;
            for (Method candidate : connections.getMethods()) {
                Class<?>[] types = candidate.getParameterTypes();
                if (candidate.getName().equals("setProxySettings") && types.length == 2 && types[0] == boolean.class) {
                    setter = candidate; break;
                }
            }
            if (setter == null) throw new NoSuchMethodException("Unsupported Telegram proxy API");
            Class<?> settingsClass = setter.getParameterTypes()[1];
            Object settings = null;
            for (Method factory : settingsClass.getDeclaredMethods()) {
                Class<?>[] types = factory.getParameterTypes();
                if (Modifier.isStatic(factory.getModifiers()) && factory.getReturnType() == settingsClass &&
                    types.length == 1 && types[0] == SharedPreferences.class) {
                    factory.setAccessible(true); settings = factory.invoke(null, prefs); break;
                }
            }
            if (settings == null) throw new NoSuchMethodException("Unsupported Telegram proxy settings");
            Class<?> infoClass = Class.forName("org.telegram.messenger.SharedConfig$ProxyInfo");
            Object info = infoClass.getConstructor(settingsClass).newInstance(settings);
            info = shared.getMethod("addProxy", infoClass).invoke(null, info);
            shared.getField("currentProxy").set(null, info);
            setter.invoke(null, enabled, settings);
        }
    }
}
