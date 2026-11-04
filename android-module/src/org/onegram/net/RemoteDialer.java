package org.onegram.net;

import java.io.Closeable;
import java.io.IOException;
import java.util.*;
import java.util.concurrent.*;

final class RemoteDialer {
    private static final ThreadPoolExecutor POOL = new ThreadPoolExecutor(8, 8, 30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(128), runnable -> {
            Thread thread = new Thread(runnable, "OneGram TLS connection"); thread.setDaemon(true); return thread;
        });
    static { POOL.allowCoreThreadTimeOut(true); }

    interface Connector { LocalProxy.Remote connect(Scope scope) throws Exception; }
    static final class Attempt {
        final String name;
        final long delay;
        final Connector connector;
        Attempt(String name, long delay, Connector connector) { this.name=name; this.delay=delay; this.connector=connector; }
    }
    static final class Scope {
        private boolean cancelled;
        private final List<Closeable> sockets = new ArrayList<>();
        synchronized <T extends Closeable> T own(T socket) throws IOException {
            if (cancelled) { LocalProxy.closeQuietly(socket); throw new IOException("Connection attempt cancelled"); }
            sockets.add(socket); return socket;
        }
        synchronized void check() throws IOException {
            if (cancelled) throw new IOException("Connection attempt cancelled");
        }
        void cancel() {
            List<Closeable> copy;
            synchronized(this) { cancelled=true; copy=new ArrayList<>(sockets); sockets.clear(); }
            for (Closeable socket:copy) LocalProxy.closeQuietly(socket);
        }
    }
    private static final class Result {
        final LocalProxy.Remote remote;
        final Scope scope;
        Result(LocalProxy.Remote remote, Scope scope) { this.remote=remote; this.scope=scope; }
    }
    static LocalProxy.Remote connect(List<Attempt> attempts, long timeoutMillis) throws Exception {
        ExecutorCompletionService<Result> completed = new ExecutorCompletionService<>(POOL);
        List<Scope> scopes = new ArrayList<>();
        List<Future<Result>> futures = new ArrayList<>();
        Scope winner = null;
        Exception failure = null;
        long deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(timeoutMillis);
        try {
            for (Attempt attempt:attempts) {
                Scope scope = new Scope();
                try {
                    Future<Result> task = completed.submit(() -> {
                        try {
                            if (attempt.delay>0) Thread.sleep(attempt.delay);
                            scope.check();
                            LocalProxy.Remote remote=attempt.connector.connect(scope);
                            scope.own(remote);
                            scope.check();
                            return new Result(remote,scope);
                        } catch(Exception error) {
                            scope.cancel();
                            throw new IOException(attempt.name+": "+error.getClass().getSimpleName(),error);
                        }
                    });
                    scopes.add(scope); futures.add(task);
                } catch(RejectedExecutionException full) { scope.cancel(); failure=full; }
            }
            for (int remaining=futures.size(); remaining>0; remaining--) {
                long wait=deadline-System.nanoTime();
                if (wait<=0) break;
                Future<Result> ready=completed.poll(wait,TimeUnit.NANOSECONDS);
                if (ready==null) break;
                try {
                    Result result=ready.get();
                    winner=result.scope;
                    return result.remote;
                } catch(ExecutionException error) {
                    failure=error.getCause() instanceof Exception ? (Exception)error.getCause() : error;
                }
            }
            throw new IOException("WebSocket routes unavailable"+(failure==null?": timeout":": "+failure.getMessage()),failure);
        } finally {
            for (int i=0;i<scopes.size();i++) if (scopes.get(i)!=winner) {
                scopes.get(i).cancel(); futures.get(i).cancel(true);
            }
            POOL.purge();
        }
    }
}
