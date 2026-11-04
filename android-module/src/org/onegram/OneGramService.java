package org.onegram;

import android.app.*;
import android.content.*;
import android.net.*;
import android.os.*;
import android.util.Log;
import java.util.*;
import java.util.concurrent.*;
import org.onegram.net.LocalProxy;
import org.onegram.net.ProxyRuntime;
import org.onegram.net.ProxyEndpoints;

public final class OneGramService extends Service {
    public static final String ACTION_RESUME="org.onegram.RESUME_CONNECTION";
    public static final String ACTION_RECONNECT="org.onegram.RECONNECT";
    private static final int NOTIFICATION=30731;
    private static final String CHANNEL="onegram_connection";
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final ExecutorService refresh=Executors.newSingleThreadExecutor(runnable->{Thread thread=new Thread(runnable,"OneGram endpoints");thread.setDaemon(true);return thread;});
    private ProxyRuntime runtime;
    private SharedPreferences prefs;
    private NotificationManager notifications;
    private ConnectivityManager connectivity;
    private ConnectivityManager.NetworkCallback networkCallback;
    private Network currentNetwork;
    private boolean destroyed,refreshing;
    private long lastFeedAttempt;
    private String shown="";

    public void onCreate() {
        super.onCreate();
        if(!OneGramConfig.proxyEnabled()){stopSelf();return;}
        notifications=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);
        notifications.createNotificationChannel(new NotificationChannel(CHANNEL,"OneGram: подключение",NotificationManager.IMPORTANCE_LOW));
        Notification initial=notification("Запуск подключения…");
        if(Build.VERSION.SDK_INT>=34)startForeground(NOTIFICATION,initial,0x40000000);
        else startForeground(NOTIFICATION,initial);
        prefs=getSharedPreferences("onegram",MODE_PRIVATE);
        okhttp3.OkHttp.INSTANCE.initialize(getApplicationContext());
        ProxyEndpoints.replace(ProxyEndpoints.parse(prefs.getString("fallback_domains",""),false));
        runtime=new ProxyRuntime(new ProxyRuntime.Store(){
            public String secret(){return prefs.getString("proxy_secret","");}
            public int port(){return prefs.getInt("proxy_port",0);}
            public void save(String secret,int port){prefs.edit().putString("proxy_secret",secret).putInt("proxy_port",port).commit();}
            public void apply(int port,String secret)throws Exception{OneGramBoot.configureProxy(OneGramService.this,port,secret);}
        });
        connectivity=(ConnectivityManager)getSystemService(CONNECTIVITY_SERVICE);
        networkCallback=new ConnectivityManager.NetworkCallback(){
            public void onAvailable(Network network){handler.post(()->{
                if(destroyed||network.equals(currentNetwork))return;
                currentNetwork=network;networkChanged();
            });}
            public void onLost(Network network){handler.post(()->{
                if(destroyed||!network.equals(currentNetwork))return;
                currentNetwork=null;networkChanged();
            });}
        };
        try{connectivity.registerDefaultNetworkCallback(networkCallback);}
        catch(RuntimeException error){Log.w("OneGram","Cannot monitor network changes",error);networkCallback=null;}
        handler.post(tick);
        refreshEndpoints();
    }

    private final Runnable tick=new Runnable(){public void run(){
        if(destroyed)return;
        if(!OneGramConfig.proxyEnabled()){stopSelf();return;}
        runtime.ensure(false);updateStatus();refreshEndpoints();handler.postDelayed(this,5000);
    }};

    private void networkChanged(){
        if(!OneGramConfig.proxyEnabled())return;
        ProxyEndpoints.networkChanged();runtime.reconnect();runtime.ensure(true);updateStatus();refreshEndpoints();
    }
    private void refreshEndpoints(){
        long now=SystemClock.elapsedRealtime();
        if(refreshing || (lastFeedAttempt>0&&now-lastFeedAttempt<300000)
                || System.currentTimeMillis()-prefs.getLong("fallback_updated",0)<3600000)return;
        refreshing=true;lastFeedAttempt=now;
        refresh.execute(()->{
            try{
                List<String> fresh=ProxyEndpoints.refresh();
                prefs.edit().putString("fallback_domains",String.join("\n",fresh)).putLong("fallback_updated",System.currentTimeMillis()).apply();
            }catch(Exception error){Log.w("OneGram","Keeping bundled reserve endpoints: "+error.getClass().getSimpleName());}
            finally{handler.post(()->refreshing=false);}
        });
    }

    public int onStartCommand(Intent intent,int flags,int id){
        if(!OneGramConfig.proxyEnabled()){try{OneGramBoot.disableProxy(this);}catch(Exception error){Log.w("OneGram","Cannot disable proxy",error);}
            stopSelf();return START_NOT_STICKY;}
        if(intent!=null && ACTION_RECONNECT.equals(intent.getAction())){
            runtime.reconnect();runtime.ensure(true);
        }else if(intent!=null && ACTION_RESUME.equals(intent.getAction()))runtime.wake(SystemClock.elapsedRealtime());
        else runtime.ensure(true);
        updateStatus();return START_STICKY;
    }
    private void updateStatus(){
        LocalProxy proxy=runtime.proxy();
        String status;
        String error=runtime.lastError;
        if(!runtime.configured()||proxy==null)status="Не удалось запустить подключение. Нажми «Переподключить».";
        else if(proxy.activeHttpMedia.get()>0)status="HTTP/2: загрузка медиа";
        else if(proxy.activeWebSockets.get()>0)status=proxy.activeFallbackWebSockets.get()>0?"WebSocket: резервный маршрут":"WebSocket Telegram";
        else if(proxy.activeConnections()>0)status="Резервный TCP: ожидание ответа Telegram";
        else if(!proxy.lastError.isEmpty()){status="Нет соединения с Telegram. Нажми «Переподключить».";error=proxy.lastError;}
        else status="Прокси запущен: подключаем Telegram…";
        if(!status.equals(shown)){
            shown=status;notifications.notify(NOTIFICATION,notification(status));
            prefs.edit().putBoolean("proxy_running",runtime.configured()).putString("connection_status",status)
                .putString("connection_error",error).apply();
            if(!error.isEmpty())Log.w("OneGram","Connection status: "+error);
        }
    }
    private Notification notification(String text){
        Intent open=new Intent();open.setClassName(getPackageName(),"org.telegram.ui.LaunchActivity");
        open.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP|Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent click=PendingIntent.getActivity(this,0,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        Intent restart=new Intent(this,OneGramService.class).setAction(ACTION_RECONNECT);
        PendingIntent retry=PendingIntent.getForegroundService(this,1,restart,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        int icon=getResources().getIdentifier("onegram_status","drawable",getPackageName());
        if(icon==0)icon=android.R.drawable.stat_notify_sync_noanim;
        return new Notification.Builder(this,CHANNEL).setSmallIcon(icon).setContentTitle("OneGram").setContentText(text)
            .setStyle(new Notification.BigTextStyle().bigText(text)).setContentIntent(click)
            .addAction(android.R.drawable.ic_popup_sync,"Переподключить",retry).setOnlyAlertOnce(true)
            .setOngoing(true).setShowWhen(false).setCategory(Notification.CATEGORY_SERVICE).build();
    }
    public IBinder onBind(Intent intent){return null;}
    public void onDestroy(){
        destroyed=true;handler.removeCallbacksAndMessages(null);refresh.shutdownNow();
        if(networkCallback!=null)try{connectivity.unregisterNetworkCallback(networkCallback);}catch(RuntimeException ignored){}
        if(runtime!=null)runtime.close();
        if(prefs!=null)prefs.edit().putBoolean("proxy_running",false).apply();
        stopForeground(true);super.onDestroy();
    }
}
