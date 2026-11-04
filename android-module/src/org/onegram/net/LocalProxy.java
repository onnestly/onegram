package org.onegram.net;

import java.io.*;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicLong;
import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import javax.net.ssl.*;

public final class LocalProxy implements Closeable {
    private static final int LIMIT = 8 * 1024 * 1024;
    private static final SecureRandom RANDOM = new SecureRandom();
    private final byte[] secret;
    private final ServerSocket listener;
    private final Set<Socket> clients = ConcurrentHashMap.newKeySet();
    private final Set<Remote> remotes = ConcurrentHashMap.newKeySet();
    private final ExecutorService workers = Executors.newCachedThreadPool(r -> {
        Thread t = new Thread(r, "OneGram connection"); t.setDaemon(true); return t;
    });
    private final Semaphore capacity = new Semaphore(24);
    private final RemoteFactory factory;
    private final Thread acceptThread;
    public final AtomicLong bytesUp = new AtomicLong();
    public final AtomicLong bytesDown = new AtomicLong();
    public final AtomicLong websocketConnections = new AtomicLong();
    public final AtomicLong fallbackConnections = new AtomicLong();
    public final AtomicLong activeWebSockets = new AtomicLong();
    public final AtomicLong activeFallbackWebSockets = new AtomicLong();
    public final AtomicLong activeHttpMedia = new AtomicLong();
    public volatile String lastTransport = "Ожидание Telegram";
    public volatile String lastError = "";
    private volatile boolean closed;

    public interface Remote extends Closeable {
        void send(byte[] data) throws Exception;
        byte[] receive() throws Exception;
        default String transport() { return "Тестовое соединение"; }
    }
    public interface RemoteFactory {
        Remote connect(int dc, boolean media, boolean test) throws Exception;
    }

    public LocalProxy(byte[] secret) throws IOException {
        this(secret, 0, LocalProxy::connectTelegram);
    }

    public LocalProxy(byte[] secret, int port) throws IOException {
        this(secret, port, LocalProxy::connectTelegram);
    }

    public LocalProxy(byte[] secret, RemoteFactory factory) throws IOException {
        this(secret, 0, factory);
    }

    public LocalProxy(byte[] secret, int port, RemoteFactory factory) throws IOException {
        if (secret.length != 16) throw new IllegalArgumentException("Secret must be 16 bytes");
        this.secret = secret.clone();
        this.factory = factory;
        listener = new ServerSocket();
        try {
            listener.setReuseAddress(true);
            listener.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), port), 32);
        } catch (IOException error) { listener.close(); workers.shutdownNow(); throw error; }
        acceptThread = new Thread(this::accept, "OneGram listener");
        acceptThread.setDaemon(true);
        acceptThread.start();
    }

    public int getPort() { return listener.getLocalPort(); }
    public boolean isHealthy() { return !closed && !listener.isClosed() && acceptThread.isAlive() && !workers.isShutdown(); }
    public int activeConnections() { return remotes.size(); }
    public int activeClients() { return clients.size(); }
    public void reconnect() {
        for (Socket client:clients) closeQuietly(client);
        for (Remote remote:remotes) closeQuietly(remote);
        lastTransport="Переподключение";
    }

    private void accept() {
        while (!closed) {
            try {
                Socket client = listener.accept();
                if (!capacity.tryAcquire()) { client.close(); continue; }
                clients.add(client);
                workers.execute(() -> handle(client));
            } catch (IOException | RejectedExecutionException e) {
                if (!closed) lastError = e.getClass().getSimpleName();
            }
        }
    }

    private void handle(Socket client) {
        Remote remote = null;
        boolean countedWebSocket = false;
        boolean countedFallback = false;
        boolean countedHttp = false;
        try {
            client.setTcpNoDelay(true);
            client.setSoTimeout(10000);
            InputStream raw = client.getInputStream();
            byte[] init = read(raw, 64);
            byte[] material = Arrays.copyOfRange(init, 8, 56);
            Cipher fromClient = aes(hash(concat(Arrays.copyOf(material, 32), secret)), Arrays.copyOfRange(material, 32, 48));
            byte[] decoded = fromClient.update(init);
            int protocol = little(decoded, 56);
            if (protocol != 0xeeeeeeee && protocol != 0xdddddddd && protocol != 0xefefefef)
                throw new IOException("Invalid local handshake");
            int signedDc = (short) ((decoded[60] & 255) | ((decoded[61] & 255) << 8));
            int dc = Math.abs(signedDc);
            boolean test = dc >= 10000;
            if (test) dc -= 10000;
            if (dc < 1 || (dc > 5 && dc != 203)) throw new IOException("Unknown datacenter");
            boolean media = signedDc < 0;
            byte[] reverse = reverse(material);
            Cipher toClient = aes(hash(concat(Arrays.copyOf(reverse, 32), secret)), Arrays.copyOfRange(reverse, 32, 48));
            byte[] relay = relayInit(protocol, signedDc);
            byte[] relayMaterial = Arrays.copyOfRange(relay, 8, 56);
            Cipher toTelegram = aes(Arrays.copyOf(relayMaterial, 32), Arrays.copyOfRange(relayMaterial, 32, 48));
            toTelegram.update(new byte[64]);
            reverse = reverse(relayMaterial);
            Cipher fromTelegram = aes(Arrays.copyOf(reverse, 32), Arrays.copyOfRange(reverse, 32, 48));
            remote = factory.connect(dc, media, test);
            remotes.add(remote);
            if (client.isClosed() || closed) throw new IOException("Local connection was reset");
            remote.send(relay);
            lastTransport=remote.transport(); lastError="";
            if(remote instanceof HttpMediaRemote){activeHttpMedia.incrementAndGet();countedHttp=true;}
            if (remote instanceof WebSocketRemote) {
                websocketConnections.incrementAndGet(); activeWebSockets.incrementAndGet(); countedWebSocket=true;
                if (((WebSocketRemote)remote).fallbackDomain!=null) {
                    fallbackConnections.incrementAndGet();activeFallbackWebSockets.incrementAndGet();countedFallback=true;
                }
            }
            client.setSoTimeout(0);
            final Remote upstream = remote;
            Thread download = new Thread(() -> {
                try {
                    OutputStream output = client.getOutputStream();
                    byte[] data;
                    while ((data = upstream.receive()) != null) {
                        if (data.length == 0) continue;
                        byte[] plain = fromTelegram.update(data);
                        output.write(toClient.update(plain));
                        output.flush();
                        bytesDown.addAndGet(data.length);
                    }
                } catch (Exception error) {
                    if (!closed && !client.isClosed()) lastError=error.getClass().getSimpleName();
                } finally {
                    closeQuietly(client);
                }
            }, "OneGram download");
            download.setDaemon(true);
            download.start();
            InputStream plain = new FilterInputStream(raw) {
                public int read() throws IOException {
                    byte[] one = new byte[1];
                    return read(one, 0, 1) < 0 ? -1 : one[0] & 255;
                }
                public int read(byte[] bytes, int offset, int count) throws IOException {
                    int length = super.read(bytes, offset, count);
                    if (length > 0) {
                        byte[] result = fromClient.update(bytes, offset, length);
                        System.arraycopy(result, 0, bytes, offset, length);
                    }
                    return length;
                }
            };
            while (!closed && !client.isClosed()) {
                byte[] packet = readPacket(plain, protocol);
                upstream.send(toTelegram.update(packet));
                bytesUp.addAndGet(packet.length);
            }
        } catch (Exception e) {
            if (!(e instanceof EOFException) && !closed && !client.isClosed()) lastError = e.getClass().getSimpleName()+": "+String.valueOf(e.getMessage());
        } finally {
            if (countedWebSocket) activeWebSockets.decrementAndGet();
            if (countedFallback) activeFallbackWebSockets.decrementAndGet();
            if (countedHttp) activeHttpMedia.decrementAndGet();
            if (remote != null) { remotes.remove(remote); closeQuietly(remote); }
            clients.remove(client);
            closeQuietly(client);
            capacity.release();
        }
    }

    private static byte[] readPacket(InputStream input, int protocol) throws IOException {
        byte[] header;
        int size;
        if (protocol == 0xefefefef) {
            int first = input.read();
            if (first < 0) throw new EOFException();
            if (first == 0x7f || first == 0xff) {
                byte[] rest = read(input, 3);
                header = concat(new byte[]{(byte) first}, rest);
                size = ((rest[0] & 255) | ((rest[1] & 255) << 8) | ((rest[2] & 255) << 16)) * 4;
            } else {
                header = new byte[]{(byte) first};
                size = (first & 0x7f) * 4;
            }
        } else {
            header = read(input, 4);
            size = little(header, 0) & 0x7fffffff;
        }
        if (size <= 0 || size > LIMIT) throw new IOException("Invalid packet size");
        return concat(header, read(input, size));
    }

    static byte[] relayInit(int protocol, int dc) throws Exception {
        byte[] init = new byte[64];
        do { RANDOM.nextBytes(init); } while ((init[0] & 255) == 0xef ||
            little(init, 0) == 0x44414548 || little(init, 0) == 0x54534f50 ||
            little(init, 0) == 0x20544547 || little(init, 0) == 0x4954504f ||
            little(init, 0) == 0xeeeeeeee || little(init, 0) == 0xdddddddd ||
            little(init, 0) == 0x02010316 || little(init, 4) == 0);
        ByteBuffer.wrap(init).order(ByteOrder.LITTLE_ENDIAN).putInt(56, protocol).putShort(60, (short) dc);
        Cipher encryption = aes(Arrays.copyOfRange(init, 8, 40), Arrays.copyOfRange(init, 40, 56));
        byte[] encrypted = encryption.update(init);
        System.arraycopy(encrypted, 56, init, 56, 8);
        return init;
    }

    private static Remote connectTelegram(int dc, boolean media, boolean test) throws Exception {
        return connectTelegram(dc,media,test,false);
    }

    static Remote connectFallback(int dc, boolean media, boolean test) throws Exception {
        return connectTelegram(dc,media,test,true);
    }

    private static Remote connectTelegram(int dc, boolean media, boolean test, boolean fallbackOnly) throws Exception {
        int hostnameDc = dc == 203 ? 2 : dc;
        String fallback = ip(dc, test);
        String target = !test && dc == 4 ? "149.154.167.220" : fallback;
        String[] domains = media ? new String[]{"kws" + hostnameDc + "-1.web.telegram.org", "kws" + hostnameDc + ".web.telegram.org"}
                                 : new String[]{"kws" + hostnameDc + ".web.telegram.org"};
        List<RemoteDialer.Attempt> attempts=new ArrayList<>();
        String path=test?"/apiws_test":"/apiws";
        if(media&&!test)for(String base:ProxyEndpoints.select(3)){
            String host="kws"+dc+"."+base;
            attempts.add(new RemoteDialer.Attempt("Media HTTP2",0,scope->new HttpMediaRemote(host,scope)));
        }
        if (!fallbackOnly) {
            for (String domain:domains) {
                if(target!=null)attempts.add(new RemoteDialer.Attempt("Telegram direct",media?700:0,
                    scope->new WebSocketRemote(target,domain,path,null,scope)));
            }
            String domain=domains[0];
            attempts.add(new RemoteDialer.Attempt("Telegram DNS",media?700:0,
                scope->new WebSocketRemote(domain,domain,path,null,scope)));
        }
        if (!test) for(String base:ProxyEndpoints.select(3)) {
            String host="kws"+dc+"."+base;
            attempts.add(new RemoteDialer.Attempt("Reserve WebSocket",media?700:(fallbackOnly?0:300),
                scope->new WebSocketRemote(host,host,path,base,scope)));
        }
        try {
            Remote chosen=RemoteDialer.connect(attempts,12000);
            if(chosen instanceof WebSocketRemote) {
                String base=((WebSocketRemote)chosen).fallbackDomain;
                if(base!=null)ProxyEndpoints.succeeded(base);
            }
            return chosen;
        } catch(Exception failure) {
            if(fallbackOnly || fallback==null)throw failure;
        }
        return new TcpRemote(fallback);
    }

    private static String ip(int dc, boolean test) {
        if (test) {
            if (dc == 1) return "149.154.175.10";
            if (dc == 2) return "149.154.167.40";
            if (dc == 3) return "149.154.175.117";
            return null;
        }
        switch (dc) {
            case 1: return "149.154.175.50";
            case 2: return "149.154.167.51";
            case 3: return "149.154.175.100";
            case 4: return "149.154.167.91";
            case 5: return "149.154.171.5";
            case 203: return "91.105.192.100";
            default: return null;
        }
    }

    private static class TcpRemote implements Remote {
        final Socket socket;
        TcpRemote(String host) throws IOException {
            socket = new Socket();
            try { socket.connect(new InetSocketAddress(host, 443), 6000); socket.setTcpNoDelay(true); }
            catch (IOException e) { socket.close(); throw e; }
        }
        public void send(byte[] data) throws IOException { socket.getOutputStream().write(data); }
        public byte[] receive() throws IOException {
            byte[] bytes = new byte[65536];
            int count = socket.getInputStream().read(bytes);
            return count < 0 ? null : Arrays.copyOf(bytes, count);
        }
        public void close() throws IOException { socket.close(); }
        public String transport() { return "Резервный TCP"; }
    }

    private static final class WebSocketRemote implements Remote {
        final Socket socket;
        final InputStream input;
        final OutputStream output;
        boolean fragmented;
        final String fallbackDomain;
        WebSocketRemote(String ip, String host, String path, String fallbackDomain, RemoteDialer.Scope scope) throws Exception {
            this.fallbackDomain=fallbackDomain;
            Socket raw = scope.own(new Socket());
            Socket connected = raw;
            try {
                raw.connect(new InetSocketAddress(ip, 443), 4000);
                raw.setTcpNoDelay(true); raw.setKeepAlive(true);
                scope.check();
                SSLSocket tls = scope.own((SSLSocket) ((SSLSocketFactory) SSLSocketFactory.getDefault()).createSocket(raw, host, 443, true));
                connected = tls;
                SSLParameters params = tls.getSSLParameters();
                params.setEndpointIdentificationAlgorithm("HTTPS");
                params.setServerNames(Collections.singletonList(new SNIHostName(host)));
                tls.setSSLParameters(params);
                tls.setSoTimeout(5000);
                tls.startHandshake();
                InputStream in = tls.getInputStream();
                OutputStream out = tls.getOutputStream();
                byte[] nonce = new byte[16]; RANDOM.nextBytes(nonce);
                String key = Base64.getEncoder().encodeToString(nonce);
                String request = "GET " + path + " HTTP/1.1\r\nHost: " + host + "\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n" +
                    "Sec-WebSocket-Key: " + key + "\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: binary\r\n\r\n";
                out.write(request.getBytes(StandardCharsets.US_ASCII)); out.flush();
                String response = readHeaders(in);
                String[] lines = response.split("\r\n");
                if (!lines[0].matches("HTTP/1\\.[01] 101(?: .*)?")) throw new IOException("WebSocket upgrade unavailable");
                Map<String,String> headers = new HashMap<>();
                for (String line : lines) {
                    int colon = line.indexOf(':');
                    if (colon > 0) headers.put(line.substring(0, colon).toLowerCase(Locale.ROOT), line.substring(colon + 1).trim());
                }
                String expected = Base64.getEncoder().encodeToString(MessageDigest.getInstance("SHA-1").digest(
                    (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").getBytes(StandardCharsets.US_ASCII)));
                if (!expected.equals(headers.get("sec-websocket-accept")) ||
                    !"websocket".equalsIgnoreCase(headers.get("upgrade"))) throw new IOException("Invalid WebSocket response");
                tls.setSoTimeout(0);
                socket = tls; input = in; output = out;
            } catch (Exception e) { closeQuietly(connected); closeQuietly(raw); throw e; }
        }
        public void send(byte[] data) throws Exception { frame(2, data); }
        private synchronized void frame(int opcode, byte[] data) throws IOException {
            ByteArrayOutputStream buffer = new ByteArrayOutputStream(data.length + 14);
            buffer.write(0x80 | opcode);
            if (data.length < 126) buffer.write(0x80 | data.length);
            else if (data.length <= 65535) {
                buffer.write(0xfe); buffer.write(data.length >>> 8); buffer.write(data.length);
            } else {
                buffer.write(0xff);
                for (int shift = 56; shift >= 0; shift -= 8) buffer.write((int) ((long) data.length >>> shift));
            }
            byte[] mask = new byte[4]; RANDOM.nextBytes(mask); buffer.write(mask);
            for (int i = 0; i < data.length; i++) buffer.write(data[i] ^ mask[i % 4]);
            output.write(buffer.toByteArray()); output.flush();
        }
        public byte[] receive() throws Exception {
            for (;;) {
                int first = input.read();
                if (first < 0) return null;
                int second = input.read();
                if (second < 0) throw new EOFException();
                int opcode = first & 15;
                boolean fin = (first & 128) != 0;
                if ((first & 0x70) != 0 || (second & 128) != 0) throw new IOException("Invalid server frame");
                long size = second & 127;
                if (size == 126) { byte[] n = read(input, 2); size = ((n[0] & 255) << 8) | (n[1] & 255); }
                else if (size == 127) { size = ByteBuffer.wrap(read(input, 8)).getLong(); }
                if (size < 0 || size > LIMIT) throw new IOException("Oversized WebSocket frame");
                if (opcode >= 8 && (!fin || size > 125)) throw new IOException("Invalid control frame");
                byte[] payload = read(input, (int) size);
                if (opcode == 8) { frame(8, payload); return null; }
                if (opcode == 9) { frame(10, payload); continue; }
                if (opcode == 10) continue;
                if (opcode == 2) {
                    if (fragmented) throw new IOException("Invalid message sequence");
                    fragmented = !fin;
                } else if (opcode == 0) {
                    if (!fragmented) throw new IOException("Unexpected continuation");
                    fragmented = !fin;
                } else throw new IOException("Unexpected message type");
                return payload;
            }
        }
        public void close() throws IOException { socket.close(); }
        public String transport() { return fallbackDomain==null?"WebSocket Telegram":"WebSocket: резервный маршрут"; }
    }

    private static String readHeaders(InputStream input) throws IOException {
        ByteArrayOutputStream result = new ByteArrayOutputStream();
        int state = 0;
        byte[] end = new byte[]{13, 10, 13, 10};
        while (result.size() < 16384) {
            int value = input.read();
            if (value < 0) throw new EOFException();
            result.write(value);
            state = value == end[state] ? state + 1 : (value == 13 ? 1 : 0);
            if (state == 4) return new String(result.toByteArray(), StandardCharsets.US_ASCII);
        }
        throw new IOException("Oversized HTTP header");
    }
    static Cipher aes(byte[] key, byte[] iv) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/CTR/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"), new IvParameterSpec(iv));
        return cipher;
    }
    static byte[] hash(byte[] data) throws Exception { return MessageDigest.getInstance("SHA-256").digest(data); }
    static byte[] reverse(byte[] data) {
        byte[] result = new byte[data.length];
        for (int i = 0; i < data.length; i++) result[i] = data[data.length - i - 1];
        return result;
    }
    static int little(byte[] bytes, int offset) { return ByteBuffer.wrap(bytes, offset, 4).order(ByteOrder.LITTLE_ENDIAN).getInt(); }
    static byte[] concat(byte[] a, byte[] b) {
        byte[] result = Arrays.copyOf(a, a.length + b.length);
        System.arraycopy(b, 0, result, a.length, b.length); return result;
    }
    static byte[] read(InputStream input, int size) throws IOException {
        byte[] result = new byte[size];
        int offset = 0;
        while (offset < size) {
            int count = input.read(result, offset, size - offset);
            if (count < 0) throw new EOFException();
            offset += count;
        }
        return result;
    }
    static void closeQuietly(Closeable value) { try { value.close(); } catch (Exception ignored) {} }
    public void close() {
        closed = true;
        closeQuietly(listener);
        for (Socket client : clients) closeQuietly(client);
        for (Remote remote : remotes) closeQuietly(remote);
        workers.shutdownNow();
    }
}
