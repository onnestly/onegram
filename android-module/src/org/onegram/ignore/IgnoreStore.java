package org.onegram.ignore;

import android.content.Context;
import android.content.SharedPreferences;
import java.lang.reflect.Field;
import java.util.LinkedHashMap;
import java.util.Map;

public final class IgnoreStore {
    private static final java.util.concurrent.ConcurrentHashMap<String,IgnoreRules.Entry> previews = new java.util.concurrent.ConcurrentHashMap<>();
    public static Context context() throws Exception {
        return (Context)Class.forName("org.telegram.messenger.ApplicationLoader").getField("applicationContext").get(null);
    }
    public static SharedPreferences prefs() throws Exception {
        return context().getSharedPreferences("onegram_ignore", Context.MODE_PRIVATE);
    }
    public static Field findField(Object object,String name)throws Exception {
        for(Class<?> type=object.getClass();type!=null;type=type.getSuperclass()){try{Field field=type.getDeclaredField(name);field.setAccessible(true);return field;}catch(NoSuchFieldException ignored){}}
        throw new NoSuchFieldException(name);
    }
    public static Object field(Object object, String name) throws Exception {
        for(Class<?> type=object.getClass();type!=null;type=type.getSuperclass()) {
            try {Field field=type.getDeclaredField(name);field.setAccessible(true);return field.get(object);}
            catch(NoSuchFieldException ignored) {}
        }
        throw new NoSuchFieldException(name);
    }
    public static int account(Object controller) throws Exception {
        return ((Number)field(controller,"currentAccount")).intValue();
    }
    public static long owner(int account) throws Exception {
        Class<?> config=Class.forName("org.telegram.messenger.UserConfig");
        Object instance=config.getMethod("getInstance",int.class).invoke(null,account);
        return ((Number)config.getMethod("getClientUserId").invoke(instance)).longValue();
    }
    private static String key(int account,long dialog) throws Exception {return "chat."+owner(account)+"."+dialog;}
    public static IgnoreRules.Entry get(int account,long dialog) throws Exception {
        if(dialog==0||owner(account)<=0)return null;
        String key=key(account,dialog);
        IgnoreRules.Entry preview=previews.get(key);
        if(preview!=null)return preview;
        String value=prefs().getString(key,null);
        if(value==null)return null;
        try {return IgnoreRules.Entry.decode(value);}
        catch(RuntimeException corrupt) {
             
            android.util.Log.e("OneGram","Invalid local ignore metadata",corrupt);
            return new IgnoreRules.Entry(IgnoreRules.HIDDEN,0,0);
        }
    }
    public static boolean active(int account,long dialog) throws Exception {
        IgnoreRules.Entry entry=get(account,dialog);return entry!=null&&entry.active();
    }
    public static void set(int account,long dialog,IgnoreRules.Entry entry) throws Exception {
        SharedPreferences.Editor edit=prefs().edit();
        String key=key(account,dialog);
        if(entry==null||!entry.active()){edit.remove(key);edit.remove("preview."+key);edit.remove("date."+key);}
        else{
            if(get(account,dialog)==null){
                String text="";long date=0;
                try{
                    Object controller=Class.forName("org.telegram.messenger.MessagesController").getMethod("getInstance",int.class).invoke(null,account);
                    Object messages=indexValue(field(controller,"dialogMessage"),dialog);
                    if(messages instanceof java.util.List&&!((java.util.List<?>)messages).isEmpty()){
                        Object message=((java.util.List<?>)messages).get(0);Object label=field(message,"messageText");text=label==null?"":label.toString();
                        date=((Number)field(field(message,"messageOwner"),"date")).longValue();
                    }
                }catch(Exception ignored){}
                edit.putString("preview."+key,text.length()>240?text.substring(0,240):text);
                edit.putString("date."+key,Long.toString(date));
            }
            edit.putString(key,entry.persisted().encode());
        }
        if(!edit.commit())throw new java.io.IOException("Cannot persist local ignore state");
        if(entry!=null&&entry.mode==IgnoreRules.PREVIEW)previews.put(key,entry);else previews.remove(key);
    }
    public static Object indexValue(Object index,long id)throws Exception {
        for(String name:new String[]{"get","f"})try{return index.getClass().getMethod(name,long.class).invoke(index,id);}catch(NoSuchMethodException ignored){}
        throw new NoSuchMethodException("Unsupported native dialog index");
    }
    public static String preview(int account,long dialog)throws Exception {return prefs().getString("preview."+key(account,dialog),"");}
    public static long previewDate(int account,long dialog)throws Exception {try{return Long.parseLong(prefs().getString("date."+key(account,dialog),"0"));}catch(NumberFormatException error){return 0;}}
    public static Map<Long,IgnoreRules.Entry> entries(int account) throws Exception {
        String prefix="chat."+owner(account)+".";Map<Long,IgnoreRules.Entry> result=new LinkedHashMap<>();
        for(Map.Entry<String,?> row:prefs().getAll().entrySet())if(row.getKey().startsWith(prefix)){
            try {long id=Long.parseLong(row.getKey().substring(prefix.length()));IgnoreRules.Entry entry=get(account,id);if(entry!=null&&entry.active())result.put(id,entry);}
            catch(NumberFormatException ignored) {}
        }
        return result;
    }
}
