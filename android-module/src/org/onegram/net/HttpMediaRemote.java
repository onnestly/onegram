package org.onegram.net;

import java.io.*;
import java.nio.*;
import java.util.*;
import java.util.concurrent.*;
import javax.crypto.Cipher;
import okhttp3.*;

final class HttpMediaRemote implements LocalProxy.Remote {
    static final int MAX_PACKET=4*1024*1024;
    private static final Semaphore REPLY_KIB=new Semaphore(16384);
    private static final Map<HttpMediaRemote,Boolean> ALIVE=Collections.synchronizedMap(new WeakHashMap<>());
    static{
        ScheduledExecutorService timer=Executors.newSingleThreadScheduledExecutor(r->{Thread t=new Thread(r,"OneGram media polling");t.setDaemon(true);return t;});
        timer.scheduleAtFixedRate(()->{
            List<HttpMediaRemote> channels;
            synchronized(ALIVE){channels=new ArrayList<>(ALIVE.keySet());}
            for(HttpMediaRemote remote:channels)try{remote.poll();}catch(Exception ignored){}
        },1,1,TimeUnit.SECONDS);
    }
    private static volatile OkHttpClient shared;
    private static synchronized OkHttpClient client(){
        if(shared==null){
            ThreadPoolExecutor workers=new ThreadPoolExecutor(8,8,30,TimeUnit.SECONDS,new ArrayBlockingQueue<>(128),r->{Thread t=new Thread(r,"OneGram HTTP2 media");t.setDaemon(true);return t;});
            workers.allowCoreThreadTimeOut(true);
            Dispatcher dispatcher=new Dispatcher(workers);dispatcher.setMaxRequests(16);dispatcher.setMaxRequestsPerHost(8);
            shared=new OkHttpClient.Builder().dispatcher(dispatcher).connectTimeout(4,TimeUnit.SECONDS)
                .readTimeout(65,TimeUnit.SECONDS).writeTimeout(15,TimeUnit.SECONDS)
                .followRedirects(false).followSslRedirects(false).retryOnConnectionFailure(false).build();
        }
        return shared;
    }
    static void networkChanged(){OkHttpClient client=shared;if(client!=null)client.connectionPool().evictAll();}
    private static final class Reply {
        final byte[] bytes;final int credit;
        Reply(byte[] bytes,int credit){this.bytes=bytes;this.credit=credit;}
    }
    private final String endpoint;
    private final Set<Call> calls=ConcurrentHashMap.newKeySet();
    private final BlockingQueue<Reply> replies=new ArrayBlockingQueue<>(8);
    private final Semaphore slots=new Semaphore(4),requestKib=new Semaphore(8192);
    private volatile boolean closed;
    private volatile IOException failure;
    private Cipher decoder,encoder;
    private int protocol;
    private final Object replayLock=new Object();
    private byte[] replayBody;
    private long lastNativeSend;
    private volatile long lastProgress=System.nanoTime();
    private int replays;

    HttpMediaRemote(String host,RemoteDialer.Scope scope)throws Exception{
        endpoint="https://"+host+"/api";
        scope.own(this);
        Call probe=client().newCall(new Request.Builder().url(endpoint).head().build());
        probe.timeout().timeout(5,TimeUnit.SECONDS);calls.add(probe);
        try(Response response=probe.execute()){
            scope.check();
            if(response.protocol()!=Protocol.HTTP_2 || !(response.isSuccessful() || response.code()==405 || response.code()==501))
                throw new IOException("Media HTTP2 route unavailable: "+response.code());
        }finally{calls.remove(probe);}
        ALIVE.put(this,true);if(closed)ALIVE.remove(this);
    }
    public synchronized void send(byte[] data)throws Exception{
        check();
        if(decoder==null){
            if(data.length!=64)throw new IOException("Invalid media transport header");
            byte[] material=Arrays.copyOfRange(data,8,56),reverse=LocalProxy.reverse(material);
            decoder=LocalProxy.aes(Arrays.copyOf(material,32),Arrays.copyOfRange(material,32,48));
            protocol=LocalProxy.little(decoder.update(data),56);
            encoder=LocalProxy.aes(Arrays.copyOf(reverse,32),Arrays.copyOfRange(reverse,32,48));
            return;
        }
        byte[] body=body(decoder.update(data),protocol);
        synchronized(replayLock){
            replayBody=body.length<=65536?body:null;lastNativeSend=System.nanoTime();lastProgress=lastNativeSend;replays=0;
        }
        submit(body,false);
    }
    private void poll()throws Exception{
        byte[] body;
        synchronized(replayLock){
            long now=System.nanoTime();
            if(closed||failure!=null||replayBody==null||replays>=2||!calls.isEmpty()
                ||now-lastProgress<TimeUnit.SECONDS.toNanos(3)||now-lastNativeSend>TimeUnit.SECONDS.toNanos(30))return;
            body=replayBody;replays++;lastProgress=now;
        }

        submit(body,true);
    }
    private void submit(byte[] body,boolean replay)throws Exception{
        check();
        int credit=(body.length+1023)/1024;
        if(!slots.tryAcquire(replay?0:20,TimeUnit.SECONDS)){if(replay)return;throw new IOException("Media request queue timed out");}
        if(!requestKib.tryAcquire(credit,replay?0:20,TimeUnit.SECONDS)){slots.release();if(replay)return;throw new IOException("Media request buffer is full");}
        Call call=client().newCall(new Request.Builder().url(endpoint).header("Accept-Encoding","identity")
            .post(RequestBody.create(body,MediaType.get("application/octet-stream"))).build());
        call.timeout().timeout(65,TimeUnit.SECONDS);calls.add(call);
        if(closed){calls.remove(call);call.cancel();slots.release();requestKib.release(credit);check();}
        call.enqueue(new Callback(){
            public void onFailure(Call request,IOException error){complete(request,credit);if(!replay)fail(error);}
            public void onResponse(Call request,Response response){
                try(Response result=response){
                    if(result.protocol()!=Protocol.HTTP_2 || result.code()!=200 || result.body()==null)
                        throw new IOException("Media HTTP2 response: "+result.code());
                    if(result.header("Content-Type","").toLowerCase(Locale.ROOT).contains("text/html"))
                        throw new IOException("Media route returned HTML");
                    long length=result.body().contentLength();
                    if(length>MAX_PACKET)throw new IOException("Media response too large");
                    ByteArrayOutputStream output=new ByteArrayOutputStream();
                    try(InputStream input=result.body().byteStream()){
                        byte[] buffer=new byte[16384];int count;
                        while((count=input.read(buffer))!=-1){
                            if(output.size()+count>MAX_PACKET)throw new IOException("Media response too large");
                            output.write(buffer,0,count);
                        }
                    }
                    byte[] bytes=output.toByteArray();
                    lastProgress=System.nanoTime();
                    if(length>=0 && bytes.length!=length)throw new IOException("Incomplete media response");
                    if(bytes.length==0)return;
                    if(bytes.length%4!=0)throw new IOException("Unaligned media response");
                    int units=(bytes.length+1023)/1024;
                    if(!REPLY_KIB.tryAcquire(units,10,TimeUnit.SECONDS))throw new IOException("Media receive buffer full");
                    boolean accepted=false;
                    Reply pending=new Reply(bytes,units);
                    try{if(!closed)accepted=replies.offer(pending,5,TimeUnit.SECONDS);}
                    finally{if(!accepted)REPLY_KIB.release(units);}
                    if(accepted&&closed&&replies.remove(pending))REPLY_KIB.release(units);
                    if(!accepted&&!closed)throw new IOException("Media receiver stalled");
                }catch(Exception error){if(!replay)fail(error instanceof IOException?(IOException)error:new IOException(error));}
                finally{complete(request,credit);}
            }
        });
    }
    private void complete(Call call,int credit){calls.remove(call);slots.release();requestKib.release(credit);}
    private void check()throws IOException{if(failure!=null)throw failure;if(closed)throw new IOException("Media connection closed");}
    private void fail(IOException error){if(!closed){failure=error;for(Call call:calls)call.cancel();}}
    public byte[] receive()throws Exception{
        for(;;){
            check();Reply reply=replies.poll(1,TimeUnit.SECONDS);if(reply==null)continue;
            REPLY_KIB.release(reply.credit);
            return encoder.update(frame(reply.bytes,protocol));
        }
    }
    public void close(){
        closed=true;ALIVE.remove(this);for(Call call:calls)call.cancel();
        Reply reply;while((reply=replies.poll())!=null)REPLY_KIB.release(reply.credit);
    }
    public String transport(){return "HTTP/2: медиа";}

    static byte[] body(byte[] packet,int protocol)throws IOException{
        if(packet.length==0)throw new IOException("Empty media frame");
        int header=protocol==0xefefefef?((packet[0]&127)==127?4:1):4;
        if(packet.length<header)throw new IOException("Incomplete media frame");
        int length=protocol==0xefefefef?(header==1?(packet[0]&127):((packet[1]&255)|((packet[2]&255)<<8)|((packet[3]&255)<<16)))*4
            :LocalProxy.little(packet,0)&0x7fffffff;
        if(length<24 || length>MAX_PACKET+256 || packet.length!=header+length)throw new IOException("Invalid media frame");
        byte[] body=Arrays.copyOfRange(packet,header,packet.length);
        if(protocol==0xdddddddd){
            boolean plain=true;for(int i=0;i<8;i++)if(body[i]!=0)plain=false;
            int count=plain?20+LocalProxy.little(body,16):24+((body.length-24)/16)*16;
            if(count<24 || count>body.length || body.length-count>(plain?256:15))throw new IOException("Invalid media padding");
            body=Arrays.copyOf(body,count);
        }
        if(body.length%4!=0 || body.length>MAX_PACKET)throw new IOException("Invalid media packet alignment");
        return body;
    }
    static byte[] frame(byte[] body,int protocol){
        byte[] header;
        if(protocol==0xefefefef){int words=body.length/4;header=words<127?new byte[]{(byte)words}:new byte[]{127,(byte)words,(byte)(words>>8),(byte)(words>>16)};}
        else header=ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(body.length).array();
        return LocalProxy.concat(header,body);
    }
}
