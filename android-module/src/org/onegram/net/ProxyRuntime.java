package org.onegram.net;

import java.io.Closeable;
import java.net.BindException;
import java.security.SecureRandom;
import java.util.Locale;

public final class ProxyRuntime implements Closeable {
    public interface Store {
        String secret();
        int port();
        void save(String secret,int port);
        void apply(int port,String secret) throws Exception;
    }
    private final Store store;
    private LocalProxy proxy;
    private String secret;
    private boolean configured,closed;
    private long lastWake;
    public volatile String lastError="";

    public ProxyRuntime(Store store) { this.store=store; }
    public synchronized boolean ensure(boolean reapply) {
        if(closed)return false;
        try {
            if(proxy==null || !proxy.isHealthy()) {
                if(proxy!=null)proxy.close();
                configured=false;
                secret=store.secret();
                if(secret==null || !secret.matches("[a-fA-F0-9]{32}")) {
                    byte[] bytes=new byte[16];new SecureRandom().nextBytes(bytes);
                    StringBuilder text=new StringBuilder();
                    for(byte value:bytes)text.append(String.format(Locale.ROOT,"%02x",value&255));
                    secret=text.toString();
                }
                byte[] key=new byte[16];
                for(int i=0;i<key.length;i++)key[i]=(byte)Integer.parseInt(secret.substring(i*2,i*2+2),16);
                int requested=store.port();if(requested<1024||requested>65535)requested=0;
                try { proxy=new LocalProxy(key,requested); }
                catch(BindException collision) { if(requested==0)throw collision;proxy=new LocalProxy(key); }
                store.save(secret,proxy.getPort());
            }
            if(!configured||reapply) { store.apply(proxy.getPort(),secret);configured=true; }
            lastError="";return true;
        } catch(Exception error) {
            configured=false;lastError=error.getClass().getSimpleName()+": "+String.valueOf(error.getMessage());return false;
        }
    }
    public synchronized boolean wake(long now) {
        if(lastWake>0 && now-lastWake>=30000 && proxy!=null)proxy.reconnect();
        lastWake=now;return ensure(true);
    }
    public synchronized void reconnect() { if(proxy!=null)proxy.reconnect(); }
    public synchronized LocalProxy proxy() { return proxy; }
    public synchronized boolean configured() { return configured; }
    public synchronized void close() {
        closed=true;configured=false;
        if(proxy!=null){proxy.close();proxy=null;}
    }
}
