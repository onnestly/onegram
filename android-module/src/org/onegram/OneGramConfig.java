package org.onegram;

import android.content.SharedPreferences;
import org.onegram.ignore.IgnoreStore;

public final class OneGramConfig {
    public static final String VERSION = "1.0.3";
    public static SharedPreferences preferences() throws Exception {
        return IgnoreStore.context().getSharedPreferences("onegram",0);
    }
    private static String accountKey(int account,String name)throws Exception {
        return name+"."+IgnoreStore.owner(account);
    }
    public static boolean showStreaks(int account) {
        try{return preferences().getBoolean(accountKey(account,"show_streaks"),true);}
        catch(Exception error){return true;}
    }
    public static boolean hideIgnored(int account) {
        try{return preferences().getBoolean(accountKey(account,"hide_ignored"),false);}
        catch(Exception error){return false;}
    }
    public static boolean setShowStreaks(int account,boolean value)throws Exception {
        return preferences().edit().putBoolean(accountKey(account,"show_streaks"),value).commit();
    }
    public static boolean setHideIgnored(int account,boolean value)throws Exception {
        return preferences().edit().putBoolean(accountKey(account,"hide_ignored"),value).commit();
    }
    public static boolean proxyEnabled() {
        try{return preferences().getBoolean("proxy_enabled",true);}
        catch(Exception error){return true;}
    }
}
