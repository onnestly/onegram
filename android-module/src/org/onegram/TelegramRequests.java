package org.onegram;

import android.os.*;
import java.lang.reflect.*;
import java.util.concurrent.atomic.AtomicBoolean;

final class TelegramRequests {
    interface Response {void accept(Object result,Object error)throws Exception;}
    private static final Handler UI=new Handler(Looper.getMainLooper());
    static Object create(String name)throws Exception{return Class.forName("org.telegram.tgnet.TLRPC$"+name).getConstructor().newInstance();}
    static void send(int account,Object request,Response response)throws Exception {
        Class<?> delegate=Class.forName("org.telegram.tgnet.RequestDelegate");AtomicBoolean done=new AtomicBoolean();
        Object manager=Class.forName("org.telegram.tgnet.ConnectionsManager").getMethod("getInstance",int.class).invoke(null,account);
        Object callback=Proxy.newProxyInstance(delegate.getClassLoader(),new Class<?>[]{delegate},(object,method,args)->{
            if(method.getDeclaringClass()==Object.class){if(method.getName().equals("hashCode"))return System.identityHashCode(object);if(method.getName().equals("equals"))return object==args[0];return "OneGram settings request";}
            if(args!=null&&args.length==2&&done.compareAndSet(false,true))UI.post(()->{try{response.accept(args[0],args[1]);}catch(Exception error){android.util.Log.e("OneGram","Settings request callback failed",error);}});return null;
        });
        int id=((Number)manager.getClass().getMethod("sendRequest",Class.forName("org.telegram.tgnet.TLObject"),delegate).invoke(manager,request,callback)).intValue();
        UI.postDelayed(()->{if(done.compareAndSet(false,true)){try{manager.getClass().getMethod("cancelRequest",int.class,boolean.class).invoke(manager,id,true);response.accept(null,new java.io.IOException("Request timed out"));}catch(Exception error){android.util.Log.w("OneGram","Settings request timed out",error);}}},20000);
    }
}
