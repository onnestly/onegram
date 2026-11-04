package org.onegram;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.widget.Toast;
import java.lang.reflect.*;
import java.util.*;

public final class ChannelSubscription {
    private static final Handler UI = new Handler(Looper.getMainLooper());
    private static final ChannelSubscriptionState STATE = new ChannelSubscriptionState();
    private interface Response { void accept(Object result, Object error) throws Exception; }

    public static void ensure(Context source, int slot, long owner) {
        if (owner <= 0) return;
        Context context = source.getApplicationContext();
        SharedPreferences prefs = context.getSharedPreferences("onegram", Context.MODE_PRIVATE);
        String key = "channel_joined_account_" + owner;
        if (!STATE.begin(owner, prefs.getBoolean(key, false), System.currentTimeMillis())) return;
        try {
            Object resolve = create("TL_contacts_resolveUsername");
            resolve.getClass().getField("username").set(resolve, "On3Gram");
            send(slot, owner, resolve, (response, error) -> {
                if (error != null || response == null || !sameAccount(slot, owner)) {
                    failed(owner, "Cannot resolve updates channel", error); return;
                }
                Object controller = Class.forName("org.telegram.messenger.MessagesController")
                    .getMethod("getInstance", int.class).invoke(null, slot);
                ArrayList<?> chats = (ArrayList<?>)response.getClass().getField("chats").get(response);
                Object peer = response.getClass().getField("peer").get(response);
                long channelId = peer.getClass().getField("channel_id").getLong(peer);
                Object chat = null;
                for (Object item : chats) if (item.getClass().getField("id").getLong(item) == channelId) chat = item;
                if (chat == null) { failed(owner, "Resolved channel is missing", null); return; }
                controller.getClass().getMethod("putChats", ArrayList.class, boolean.class).invoke(controller, chats, false);
                if (!chat.getClass().getField("left").getBoolean(chat)) {
                    complete(context, prefs, key, owner, false); return;
                }
                Object input = create("TL_inputChannel");
                input.getClass().getField("channel_id").setLong(input, channelId);
                input.getClass().getField("access_hash").setLong(input, chat.getClass().getField("access_hash").getLong(chat));
                Object join = create("TL_channels_joinChannel");
                join.getClass().getField("channel").set(join, input);
                Toast.makeText(context, "OneGram: подписка на канал обновлений @On3Gram", Toast.LENGTH_LONG).show();
                send(slot, owner, join, (joined, joinError) -> {
                    if (joinError != null || joined == null || !sameAccount(slot, owner)) {
                        failed(owner, "Updates channel subscription failed", joinError); return;
                    }
                    Object updates;
                    try { updates = joined.getClass().getField("updates").get(joined); }
                    catch (NoSuchFieldException newer) {
                        if (Class.forName("org.telegram.tgnet.TLRPC$Updates").isInstance(joined)) updates = joined;
                        else { failed(owner, "Channel requires an additional verification", null); return; }
                    }
                    controller.getClass().getMethod("processUpdates", Class.forName("org.telegram.tgnet.TLRPC$Updates"), boolean.class)
                        .invoke(controller, updates, false);
                    complete(context, prefs, key, owner, true);
                });
            });
        } catch (Exception error) { failed(owner, "Cannot start updates channel subscription", error); }
    }

    private static Object create(String name) throws Exception {
        return Class.forName("org.telegram.tgnet.TLRPC$" + name).getConstructor().newInstance();
    }
    private static boolean sameAccount(int slot, long owner) throws Exception {
        Class<?> config = Class.forName("org.telegram.messenger.UserConfig");
        Object account = config.getMethod("getInstance", int.class).invoke(null, slot);
        return ((Number)config.getMethod("getClientUserId").invoke(account)).longValue() == owner;
    }
    private static void send(int slot, long owner, Object request, Response result) throws Exception {
        Class<?> delegate = Class.forName("org.telegram.tgnet.RequestDelegate");
        Object callback = Proxy.newProxyInstance(delegate.getClassLoader(), new Class<?>[]{delegate}, (object, method, args) -> {
            if (method.getDeclaringClass() == Object.class) {
                if (method.getName().equals("hashCode")) return System.identityHashCode(object);
                if (method.getName().equals("equals")) return object == args[0];
                return "OneGram updates channel";
            }
            if (args != null && args.length == 2) UI.post(() -> {
                try { result.accept(args[0], args[1]); }
                catch (Exception error) { failed(owner, "Updates channel callback failed", error); }
            });
            return null;
        });
        Class<?> connections = Class.forName("org.telegram.tgnet.ConnectionsManager");
        Object instance = connections.getMethod("getInstance", int.class).invoke(null, slot);
        connections.getMethod("sendRequest", Class.forName("org.telegram.tgnet.TLObject"), delegate).invoke(instance, request, callback);
    }
    private static void complete(Context context, SharedPreferences prefs, String key, long owner, boolean joined) {
        prefs.edit().putBoolean(key, true).apply();
        STATE.completed(owner);
        if (joined) Toast.makeText(context, "Канал обновлений @On3Gram добавлен. Выйти из него можно в любой момент.", Toast.LENGTH_LONG).show();
    }
    private static void failed(long owner, String message, Object error) {
        STATE.failed(owner, System.currentTimeMillis());
        Log.w("OneGram", message + (error == null ? "" : ": " + error.getClass().getSimpleName()));
    }
}
