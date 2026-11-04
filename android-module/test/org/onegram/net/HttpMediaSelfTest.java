package org.onegram.net;

import java.nio.*;
import java.util.*;

public final class HttpMediaSelfTest {
    public static void main(String[] args)throws Exception{
        for(int protocol:new int[]{0xefefefef,0xeeeeeeee,0xdddddddd}){
            byte[] encrypted=new byte[512*1024+24];new java.security.SecureRandom().nextBytes(encrypted);
            byte[] packet=HttpMediaRemote.frame(encrypted,protocol);
            if(!Arrays.equals(encrypted,HttpMediaRemote.body(packet,protocol)))throw new AssertionError("Large encrypted media packet changed");
            if(protocol==0xdddddddd){
                byte[] body=new byte[43];ByteBuffer.wrap(body).order(ByteOrder.LITTLE_ENDIAN).putInt(16,20);
                if(HttpMediaRemote.body(HttpMediaRemote.frame(body,protocol),protocol).length!=40)throw new AssertionError("Plain padding was not removed");
                byte[] padded=Arrays.copyOf(encrypted,encrypted.length+13);
                if(!Arrays.equals(encrypted,HttpMediaRemote.body(HttpMediaRemote.frame(padded,protocol),protocol)))throw new AssertionError("Encrypted padding was not removed");
            }
        }
        System.out.println("HTTP2 media framing: three protocols, 512 KiB encrypted payload and padded frames passed");
        if(!Arrays.asList(args).contains("--live"))return;
        byte[] secret=new byte[16];new java.security.SecureRandom().nextBytes(secret);
        for(int protocol:new int[]{0xefefefef,0xeeeeeeee,0xdddddddd}){
            LocalProxy.RemoteFactory factory=(dc,media,test)->{
                List<RemoteDialer.Attempt> attempts=new ArrayList<>();
                for(String base:ProxyEndpoints.select(3))attempts.add(new RemoteDialer.Attempt("HTTP2 only",0,scope->new HttpMediaRemote("kws"+dc+"."+base,scope)));
                return RemoteDialer.connect(attempts,12000);
            };
            try(LocalProxy proxy=new LocalProxy(secret,factory);LocalProxySelfTest.Client client=new LocalProxySelfTest.Client(proxy.getPort(),secret,protocol)){
                byte[] body=new byte[40],nonce=new byte[16];new java.security.SecureRandom().nextBytes(nonce);
                ByteBuffer.wrap(body).order(ByteOrder.LITTLE_ENDIAN).putLong(8,(System.currentTimeMillis()/1000)<<32).putInt(16,20).putInt(20,0xbe7e8ef1);
                System.arraycopy(nonce,0,body,24,16);
                client.send(HttpMediaRemote.frame(body,protocol));
                int size;
                if(protocol==0xefefefef){int first=client.receive(1)[0]&255;if(first==127){byte[] rest=client.receive(3);size=((rest[0]&255)|((rest[1]&255)<<8)|((rest[2]&255)<<16))*4;}else size=first*4;}
                else size=LocalProxy.little(client.receive(4),0)&0x7fffffff;
                if(size<40||size>65536)throw new AssertionError("Invalid HTTP2 Telegram reply");
                byte[] reply=client.receive(size);
                if(LocalProxy.little(reply,20)!=0x05162463||!Arrays.equals(nonce,Arrays.copyOfRange(reply,24,40)))throw new AssertionError("HTTP2 reply is not a matching Telegram resPQ");
                if(proxy.activeHttpMedia.get()==0)throw new AssertionError("Media status is missing");
                System.out.println("Real Telegram resPQ over HTTP2 /api verified; protocol="+Integer.toHexString(protocol));
            }
        }
    }
}
