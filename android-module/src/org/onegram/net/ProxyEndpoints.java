package org.onegram.net;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;

public final class ProxyEndpoints {
    private static final String FEED = "https://raw.githubusercontent.com/Flowseal/tg-ws-proxy/main/.github/cfproxy-domains.txt";
    private static volatile List<String> domains = Collections.unmodifiableList(Arrays.asList(
        "pclead.co.uk", "offshor.co.uk", "cakeisalie.co.uk", "noskomnadzor.co.uk", "lovetrue.co.uk",
        "sorokdva.co.uk", "pyatdesyatdva.co.uk", "kartoshka.co.uk", "sorokodin.co.uk", "pyatdesyatodin.co.uk",
        "notelega.co.uk", "ebally.co.uk", "nebally.co.uk", "havegreatday.co.uk", "pomogite.co.uk",
        "fixtelega.co.uk", "sadnews.co.uk", "onedaychamp.co.uk", "stopblocking.co.uk", "nothingthere.co.uk"));
    private static final AtomicLong cursor = new AtomicLong();
    private static volatile String preferred = "";

    public static boolean valid(String domain) {
        if (domain.length()>253 || !domain.matches("[a-z0-9.-]+")) return false;
        String[] labels=domain.split("\\.",-1);
        if (labels.length<2 || !labels[labels.length-1].matches("[a-z]{2,63}")) return false;
        for(String label:labels) if(label.isEmpty() || label.length()>63 || label.startsWith("-") || label.endsWith("-")) return false;
        return true;
    }
    static String decode(String value) {
        if (!value.endsWith(".com")) return value;
        String source=value.substring(0,value.length()-4);
        int letters=0;
        for(char c:source.toCharArray()) if(c>='a'&&c<='z')letters++;
        StringBuilder result=new StringBuilder();
        for(char c:source.toCharArray()) result.append(c>='a'&&c<='z' ? (char)('a'+Math.floorMod(c-'a'-letters,26)) : c);
        return result.append(".co.uk").toString();
    }
    public static List<String> parse(String text,boolean encoded) {
        LinkedHashSet<String> result=new LinkedHashSet<>();
        for(String line:text.split("\\r?\\n")) {
            String domain=line.trim().toLowerCase(Locale.ROOT);
            if(domain.isEmpty()||domain.startsWith("#"))continue;
            if(encoded)domain=decode(domain);
            if(valid(domain))result.add(domain);
            if(result.size()>=80)break;
        }
        return new ArrayList<>(result);
    }
    public static boolean replace(List<String> values) {
        List<String> safe=parse(String.join("\n",values),false);
        if(safe.size()<3)return false;
        domains=Collections.unmodifiableList(safe); return true;
    }
    public static List<String> refresh() throws Exception {
        HttpURLConnection connection=(HttpURLConnection)new URL(FEED).openConnection();
        connection.setConnectTimeout(4000); connection.setReadTimeout(4000);
        connection.setInstanceFollowRedirects(false); connection.setUseCaches(false);
        connection.setRequestProperty("User-Agent","OneGram");
        try {
            if(connection.getResponseCode()!=200)throw new IOException("Endpoint list unavailable");
            ByteArrayOutputStream body=new ByteArrayOutputStream();
            try(InputStream input=connection.getInputStream()) {
                byte[] buffer=new byte[2048]; int count;
                while((count=input.read(buffer))!=-1){body.write(buffer,0,count);if(body.size()>65536)throw new IOException("Endpoint list too large");}
            }
            List<String> fresh=parse(new String(body.toByteArray(),StandardCharsets.UTF_8),true);
            if(!replace(fresh))throw new IOException("Invalid endpoint list");
            return fresh;
        } finally { connection.disconnect(); }
    }
    public static List<String> select(int count) {
        List<String> pool=domains;
        LinkedHashSet<String> picked=new LinkedHashSet<>();
        String recent=preferred;
        if(pool.contains(recent))picked.add(recent);
        int start=(int)((cursor.getAndIncrement()&Long.MAX_VALUE)%pool.size());
        for(int i=0;i<pool.size()&&picked.size()<count;i++)picked.add(pool.get((start+i)%pool.size()));
        return new ArrayList<>(picked);
    }
    static void succeeded(String domain) { if(domains.contains(domain))preferred=domain; }
    public static void networkChanged() { preferred=""; HttpMediaRemote.networkChanged(); }
}
