package org.onegram.net;

import android.content.SharedPreferences;
import java.io.*;
import java.net.*;
import java.nio.*;
import java.security.*;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.*;

public final class ProxyDiagnostics {
    private static byte[] hash(byte[] key,byte[] secret)throws Exception {
        MessageDigest digest=MessageDigest.getInstance("SHA-256");digest.update(key);return digest.digest(secret);
    }
    private static Cipher cipher(byte[] material,byte[] secret)throws Exception {
        Cipher cipher=Cipher.getInstance("AES/CTR/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,new SecretKeySpec(hash(Arrays.copyOfRange(material,0,32),secret),"AES"),new IvParameterSpec(Arrays.copyOfRange(material,32,48)));return cipher;
    }
    private static byte[] read(InputStream stream,Cipher cipher,int count)throws Exception {
        byte[] data=new byte[count];for(int offset=0;offset<count;){int n=stream.read(data,offset,count-offset);if(n<0)throw new EOFException();offset+=n;}return cipher.update(data);
    }
    public static void check(SharedPreferences prefs)throws Exception {
        int port=prefs.getInt("proxy_port",0);String encoded=prefs.getString("proxy_secret","");
        if(port<=0||encoded.length()!=32)throw new IOException("Proxy has not started");
        byte[] secret=new byte[16];for(int i=0;i<16;i++)secret[i]=(byte)Integer.parseInt(encoded.substring(i*2,i*2+2),16);
        byte[] init=new byte[64];new SecureRandom().nextBytes(init);init[0]=0x16;
        Arrays.fill(init,56,60,(byte)0xee);init[60]=2;init[61]=0;
        byte[] material=Arrays.copyOfRange(init,8,56),reverse=new byte[48];for(int i=0;i<48;i++)reverse[i]=material[47-i];
        Cipher outbound=cipher(material,secret),inbound=cipher(reverse,secret);byte[] encrypted=outbound.update(init);System.arraycopy(encrypted,56,init,56,8);
        byte[] nonce=new byte[16];new SecureRandom().nextBytes(nonce);
        ByteBuffer message=ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN);message.putInt(40).putLong(0).putLong((System.currentTimeMillis()/1000)<<32).putInt(20).putInt(0xbe7e8ef1).put(nonce);
        try(Socket socket=new Socket()){
            socket.connect(new InetSocketAddress("127.0.0.1",port),3000);socket.setSoTimeout(15000);
            OutputStream output=socket.getOutputStream();output.write(init);output.write(outbound.update(message.array()));output.flush();
            int size=ByteBuffer.wrap(read(socket.getInputStream(),inbound,4)).order(ByteOrder.LITTLE_ENDIAN).getInt()&0x7fffffff;
            if(size<40||size>65536)throw new IOException("Invalid Telegram reply");
            byte[] reply=read(socket.getInputStream(),inbound,size);
            if(ByteBuffer.wrap(reply).order(ByteOrder.LITTLE_ENDIAN).getInt(20)!=0x05162463||!Arrays.equals(nonce,Arrays.copyOfRange(reply,24,40)))throw new IOException("Invalid Telegram nonce");
        }
    }
}
