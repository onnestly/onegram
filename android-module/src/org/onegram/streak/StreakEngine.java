package org.onegram.streak;

import android.content.*;
import android.database.Cursor;
import android.database.sqlite.*;
import android.view.View;
import java.lang.ref.WeakReference;
import java.lang.reflect.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;

public final class StreakEngine {
    private final SQLiteDatabase database;
    private final ScheduledThreadPoolExecutor queue;
    private final Map<String,State> states = new HashMap<>();
    private final ZoneId zone = ZoneId.systemDefault();
    private long nextRequest;
    private volatile String focused="";
    private volatile boolean active = true;
    private static final class State {
        final int account; final long peer,owner;
        final Map<Long,Integer> days = new HashMap<>();
        final List<WeakReference<View>> views = new ArrayList<>();
        long covered = Long.MAX_VALUE;
        long newest, previousNewest, previousCovered;
        boolean previousExhausted;
        int offset, pages;
        int generation;
        boolean resume;
        boolean exhausted, loaded, busy;
        volatile boolean disposed;
        long refreshed;
        long scanDay; int scanSide, scanMask; boolean scanFailed;
        final Map<Long,Integer> checked = new HashMap<>();
        volatile int result = -1;
        volatile long activeDay=Long.MIN_VALUE;
        State(int account, long owner,long peer) { this.account=account;this.owner=owner; this.peer=peer; }
    }
    public StreakEngine(Context context) {
        database = context.openOrCreateDatabase("onegram_streaks.db", Context.MODE_PRIVATE, null);
        database.execSQL("CREATE TABLE IF NOT EXISTS messages(account INTEGER,peer INTEGER,id INTEGER,date INTEGER,side INTEGER,PRIMARY KEY(account,peer,id))");
        database.execSQL("CREATE TABLE IF NOT EXISTS coverage(account INTEGER,peer INTEGER,since INTEGER,exhausted INTEGER,PRIMARY KEY(account,peer))");
        database.execSQL("CREATE TABLE IF NOT EXISTS checked_days(owner INTEGER,peer INTEGER,day INTEGER,mask INTEGER,PRIMARY KEY(owner,peer,day))");
        queue = new ScheduledThreadPoolExecutor(1, runnable -> { Thread thread=new Thread(runnable,"OneGram streak history");thread.setDaemon(true);return thread; });
        queue.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
    }
    public synchronized int get(int account, long peer, View view) {
        if (!active || peer<=0) return 0;
        long owner;
        try{Class<?> config=Class.forName("org.telegram.messenger.UserConfig");Object current=config.getMethod("getInstance",int.class).invoke(null,account);owner=((Number)config.getMethod("getClientUserId").invoke(current)).longValue();}catch(Exception e){return 0;}
        if(owner<=0||owner==peer)return 0;
        String key=account+":"+owner+":"+peer;
        State state=states.get(key);
        if(state==null){state=new State(account,owner,peer);states.put(key,state);}
        boolean found=false;
        for(Iterator<WeakReference<View>> it=state.views.iterator();it.hasNext();){View v=it.next().get();if(v==null)it.remove();else if(v==view)found=true;}
        if(!found)state.views.add(new WeakReference<>(view));
        if(!state.busy && System.currentTimeMillis()-state.refreshed>60000){
            state.busy=true;State selected=state;queue.execute(()->start(selected));
        }
        return state.result;
    }
    private void start(State state) {
        if(!active||state.disposed)return;
        try {
            if(!state.loaded){
                try(Cursor cursor=database.rawQuery("SELECT date,side FROM messages WHERE account=? AND peer=?",new String[]{""+state.owner,""+state.peer})){
                    while(cursor.moveToNext())addDay(state,cursor.getLong(0),cursor.getInt(1));
                }
                try(Cursor cursor=database.rawQuery("SELECT since,exhausted FROM coverage WHERE account=? AND peer=?",new String[]{""+state.owner,""+state.peer})){
                    if(cursor.moveToFirst()){state.covered=cursor.getLong(0);state.exhausted=cursor.getInt(1)!=0;}
                }
                try(Cursor cursor=database.rawQuery("SELECT day,mask FROM checked_days WHERE owner=? AND peer=?",new String[]{""+state.owner,""+state.peer})){
                    while(cursor.moveToNext()){long day=cursor.getLong(0);int mask=cursor.getInt(1);state.checked.put(day,mask);state.days.put(day,mask);}
                }
                state.loaded=true;
            }
            Class<?> config=Class.forName("org.telegram.messenger.UserConfig");
            Object userConfig=config.getMethod("getInstance",int.class).invoke(null,state.account);
            long own=((Number)config.getMethod("getClientUserId").invoke(userConfig)).longValue();
            if(own==state.peer || own==0 || own!=state.owner){finish(state,0);return;}
            Object controller=Class.forName("org.telegram.messenger.MessagesController").getMethod("getInstance",int.class).invoke(null,state.account);
            Object user=numberMethod(controller,"getUser",state.peer);
            if(user==null){finish(state,-1);return;}
            if(user.getClass().getField("bot").getBoolean(user)){finish(state,0);return;}
            int cached=StreakRules.count(state.days,LocalDate.now(zone).toEpochDay(),state.covered,state.exhausted);
            if(cached>=0)publish(state,cached);
            state.scanDay=LocalDate.now(zone).toEpochDay();state.scanSide=1;state.scanMask=0;state.scanFailed=false;
            advance(state,controller);
        } catch(Exception error){failed(state,error);}
    }
    private static Object numberMethod(Object object,String name,long id)throws Exception{
        for(Method method:object.getClass().getMethods())if(method.getName().equals(name)&&method.getParameterTypes().length==1){
            Class<?> type=method.getParameterTypes()[0];
            if(type==long.class||type==Long.class)return method.invoke(object,id);
        }
        throw new NoSuchMethodException(name);
    }
    private void request(State state,Object controller)throws Exception {
        if(!active||state.disposed)return;
        final int token=++state.generation;
        Class<?> requestClass=Class.forName("org.telegram.tgnet.TLRPC$TL_messages_getHistory");
        Object request=requestClass.getConstructor().newInstance();
        requestClass.getField("peer").set(request,numberMethod(controller,"getInputPeer",state.peer));
        requestClass.getField("limit").setInt(request,32);
        requestClass.getField("offset_id").setInt(request,state.offset);
        long end=LocalDate.ofEpochDay(state.scanDay+1).atStartOfDay(zone).toEpochSecond();
        requestClass.getField("offset_date").setInt(request,(int)end);
        Class<?> delegate=Class.forName("org.telegram.tgnet.RequestDelegate");
        Object callback=Proxy.newProxyInstance(delegate.getClassLoader(),new Class<?>[]{delegate},(object,method,args)->{
            if(method.getDeclaringClass()==Object.class){if(method.getName().equals("hashCode"))return System.identityHashCode(object);if(method.getName().equals("equals"))return object==args[0];return "OneGram streak history";}
            if(active && args!=null && args.length==2){Object response=args[0],error=args[1];try{queue.execute(()->{if(state.generation!=token)return;state.generation++;accept(state,controller,response,error);});}catch(RejectedExecutionException ignored){}}
            return null;
        });
        Object connections=Class.forName("org.telegram.tgnet.ConnectionsManager").getMethod("getInstance",int.class).invoke(null,state.account);
        Method send=connections.getClass().getMethod("sendRequest",Class.forName("org.telegram.tgnet.TLObject"),delegate);
        Runnable transmit=new Runnable(){public void run(){
            if(!active||state.disposed||state.generation!=token)return;
            long delay=Math.max(0,nextRequest-android.os.SystemClock.elapsedRealtime());
            if(deferForFocused(state))delay=Math.max(delay,1200);
            if(delay>0){queue.schedule(this,delay,TimeUnit.MILLISECONDS);return;}
            nextRequest=android.os.SystemClock.elapsedRealtime()+1200;
            try{
                int id=((Number)send.invoke(connections,request,callback)).intValue();
                queue.schedule(()->{
                    if(!active||state.disposed||state.generation!=token)return;
                    state.generation++;
                    try{connections.getClass().getMethod("cancelRequest",int.class,boolean.class).invoke(connections,id,true);}catch(Exception ignored){}
                    failed(state,new java.io.IOException("History request timed out"));
                },35,TimeUnit.SECONDS);
            }catch(Exception error){state.generation++;failed(state,error);}
        }};
        queue.execute(transmit);
    }
    private void advance(State state,Object controller)throws Exception {
        long today=LocalDate.now(zone).toEpochDay();
        while(state.scanDay<today-1 && state.checked.containsKey(state.scanDay)){
            int mask=state.checked.get(state.scanDay);state.days.put(state.scanDay,mask);
            if(mask!=3){completeScan(state);return;}
            state.scanDay--;
        }
        state.scanSide=1;state.scanMask=0;state.offset=0;request(state,controller);
    }
    private void completeScan(State state){
        state.covered=state.scanDay;state.exhausted=false;state.resume=false;
        finish(state,StreakRules.count(state.days,LocalDate.now(zone).toEpochDay(),state.covered,false));
    }
    private void accept(State state,Object controller,Object response,Object error){
        if(!active||state.disposed)return;
        if(error!=null||response==null){failed(state,new java.io.IOException("Daily history RPC failed: "+String.valueOf(error)));return;}
        try{
            List<?> messages=(List<?>)response.getClass().getField("messages").get(response);
            boolean crossed=messages.isEmpty();int offset=state.offset;
            for(Object message:messages){
                int id=message.getClass().getField("id").getInt(message);
                long date=Integer.toUnsignedLong(message.getClass().getField("date").getInt(message));
                if(id>0)offset=offset==0?id:Math.min(offset,id);
                if(date<=0)continue;
                long day=StreakRules.day(date,zone);
                if(day<state.scanDay){crossed=true;continue;}
                if(day!=state.scanDay)continue;
                Object action=message.getClass().getField("action").get(message);
                if(action==null)state.scanMask|=message.getClass().getField("out").getBoolean(message)?1:2;
            }
             
            if(state.scanMask!=3 && !crossed && offset!=state.offset){state.offset=offset;request(state,controller);return;}
            if(state.scanMask!=3 && !crossed && offset==state.offset)throw new java.io.IOException("Daily history made no progress");
            state.days.put(state.scanDay,state.scanMask);state.checked.put(state.scanDay,state.scanMask);
            ContentValues row=new ContentValues();row.put("owner",state.owner);row.put("peer",state.peer);row.put("day",state.scanDay);row.put("mask",state.scanMask);
            database.insertWithOnConflict("checked_days",null,row,SQLiteDatabase.CONFLICT_REPLACE);
            state.pages++;
            publish(state,state.result);
            if(state.scanDay<LocalDate.now(zone).toEpochDay() && state.scanMask!=3){completeScan(state);return;}
            state.scanDay--;advance(state,controller);
        }catch(Exception failure){failed(state,failure);}
    }
    public synchronized int progress(){
        int total=states.size(),done=0;boolean busy=false;
        for(State state:states.values()){if(state.busy)busy=true;else if(state.refreshed>0&&!state.scanFailed)done++;}
        return !busy?-1:Math.min(99,total==0?0:done*100/total);
    }
    private void addDay(State state,long seconds,int side){state.newest=Math.max(state.newest,seconds);long day=StreakRules.day(seconds,zone);state.days.put(day,state.days.getOrDefault(day,0)|side);}
    public synchronized boolean activeToday(int account,long peer){
        long today=LocalDate.now(zone).toEpochDay();
        for(State state:states.values())if(state.account==account && state.peer==peer && state.activeDay==today)return true;
        return false;
    }
    public void focus(int account,long peer){focused=account+":"+peer;}
    private synchronized boolean deferForFocused(State current){
        for(State state:states.values())if(state!=current && state.busy && focused.equals(state.account+":"+state.peer))return true;
        return false;
    }
    private void failed(State state,Exception error){
        state.scanFailed=true;state.resume=false;
        android.util.Log.w("OneGram","Cannot finish streak history page",error);
        long coverage=state.previousNewest>0?Math.min(state.covered,state.previousCovered):state.covered;
        int cached=StreakRules.count(state.days,LocalDate.now(zone).toEpochDay(),coverage,state.exhausted||state.previousExhausted);
        finish(state,cached>=0?cached:state.result);
    }
    private synchronized void publish(State state,int count){
        if(state.disposed)return;
        long today=LocalDate.now(zone).toEpochDay();
        state.activeDay=state.days.getOrDefault(today,0)==3?today:Long.MIN_VALUE;
        state.result=count;
        for(WeakReference<View> ref:state.views){View view=ref.get();if(view!=null)view.postInvalidate();}
    }
    private synchronized void finish(State state,int count){
        publish(state,count);state.busy=false;state.refreshed=System.currentTimeMillis();
        if(focused.equals(state.account+":"+state.peer))focused="";
    }
    public synchronized void clearOwner(long owner){
        java.util.List<WeakReference<View>> invalidated=new ArrayList<>();
        for(Iterator<State> iterator=states.values().iterator();iterator.hasNext();){
            State state=iterator.next();if(state.owner!=owner)continue;
            state.disposed=true;state.generation++;invalidated.addAll(state.views);iterator.remove();
        }
        queue.execute(()->{
            Object[] args={owner};
            database.execSQL("DELETE FROM messages WHERE account=?",args);
            database.execSQL("DELETE FROM coverage WHERE account=?",args);
            database.execSQL("DELETE FROM checked_days WHERE owner=?",args);
        });
        for(WeakReference<View> reference:invalidated){View view=reference.get();if(view!=null)view.postInvalidate();}
    }
    public synchronized void close(){active=false;queue.execute(database::close);queue.shutdown();states.clear();}
}
