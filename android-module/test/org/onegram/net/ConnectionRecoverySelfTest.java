package org.onegram.net;

import java.io.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public final class ConnectionRecoverySelfTest {
    static class Store implements ProxyRuntime.Store {
        String secret="";int port,calls,failures;
        public String secret(){return secret;}
        public int port(){return port;}
        public void save(String value,int number){secret=value;port=number;}
        public void apply(int port,String secret)throws Exception{calls++;if(failures-->0)throw new IOException("Native init not ready");}
    }
    static final class Remote implements LocalProxy.Remote {
        final AtomicBoolean closed=new AtomicBoolean();
        public void send(byte[] ignored){}
        public byte[] receive(){return null;}
        public void close(){closed.set(true);}
    }
    public static void main(String[] args)throws Exception{
        Store store=new Store();store.failures=1;
        int saved;
        try(ProxyRuntime runtime=new ProxyRuntime(store)){
            check(!runtime.ensure(false),"Native setup failure must not report connected");
            saved=runtime.proxy().getPort();
            check(runtime.proxy().isHealthy(),"Keep listener for a later native setup retry");
            check(runtime.ensure(false)&&runtime.proxy().getPort()==saved,"Retry without replacing the port");
            check(store.calls==2,"Native setup retried");
            runtime.proxy().close();
            check(runtime.ensure(false)&&runtime.proxy().getPort()==saved,"Watchdog restarts a failed listener on the saved port");
            runtime.wake(1000);
            try(Socket client=new Socket("127.0.0.1",saved)){
                client.setSoTimeout(1500);
                long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(2);
                while(runtime.proxy().activeClients()==0&&System.nanoTime()<deadline)Thread.sleep(5);
                check(runtime.proxy().activeClients()==1,"Native client accepted");
                runtime.wake(40000);
                check(client.getInputStream().read()==-1,"Wake after background closes a stale tunnel");
                check(runtime.proxy().getPort()==saved,"Wake preserves proxy settings");
            }
        }
        check(store.secret.matches("[a-f0-9]{32}"),"Persistent local secret");
        try(ProxyRuntime restarted=new ProxyRuntime(store)){
            check(restarted.ensure(false)&&restarted.proxy().getPort()==saved,"Service recreation preserves native proxy address");
        }
        try(ServerSocket occupied=new ServerSocket(0,1,InetAddress.getByName("127.0.0.1"))){
            store.port=occupied.getLocalPort();
            try(ProxyRuntime runtime=new ProxyRuntime(store)){
                check(runtime.ensure(false)&&store.port!=occupied.getLocalPort(),"Occupied saved port gets a replacement and new settings");
            }
        }
        CountDownLatch started=new CountDownLatch(1),late=new CountDownLatch(1);
        AtomicBoolean slowClosed=new AtomicBoolean(),lateClosed=new AtomicBoolean();
        Remote fast=new Remote();
        List<RemoteDialer.Attempt> attempts=Arrays.asList(
            new RemoteDialer.Attempt("slow",0,scope->{
                scope.own((Closeable)()->slowClosed.set(true));started.countDown();
                try{Thread.sleep(5000);}catch(InterruptedException expected){
                    try{scope.own((Closeable)()->lateClosed.set(true));}finally{late.countDown();}
                    throw expected;
                }
                return new Remote();
            }),
            new RemoteDialer.Attempt("fast",0,scope->{check(started.await(1,TimeUnit.SECONDS),"Slow route started");return fast;}));
        check(RemoteDialer.connect(attempts,2000)==fast,"First working route selected");
        check(slowClosed.get()&&!fast.closed.get(),"Only losing route resources are closed");
        check(late.await(1,TimeUnit.SECONDS)&&lateClosed.get(),"Resources created after cancellation are closed");
        fast.close();
        AtomicBoolean timedOutClosed=new AtomicBoolean();
        try{
            RemoteDialer.connect(Collections.singletonList(new RemoteDialer.Attempt("timeout",0,scope->{
                scope.own((Closeable)()->timedOutClosed.set(true));Thread.sleep(5000);return new Remote();
            })),100);
            throw new AssertionError("Expected bounded dial timeout");
        }catch(IOException expected){check(timedOutClosed.get(),"Timeout closes pending sockets");}
        List<String> original=ProxyEndpoints.select(80);
        List<String> feed=ProxyEndpoints.parse("# feed\nvirkgj.com\nvmmzovy.com\nmkuosckvso.com\nhttp://invalid\n127.0.0.1\n",true);
        check(feed.equals(Arrays.asList("pclead.co.uk","offshor.co.uk","cakeisalie.co.uk")),"Upstream feed decoding and invalid-host filtering");
        check(!ProxyEndpoints.replace(Collections.singletonList("localhost")),"Bad feed cannot discard working fallback hosts");
        check(ProxyEndpoints.select(80).size()==original.size(),"Bundled hosts survive a malformed refresh");
        System.out.println("Recovery: native init retry, stable port, listener restart, background wake, port collision, parallel failover cancellation, timeout and endpoint validation passed");
    }
    static void check(boolean condition,String label){if(!condition)throw new AssertionError(label);}
}
