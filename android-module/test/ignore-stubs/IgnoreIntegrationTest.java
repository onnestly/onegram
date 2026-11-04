import org.onegram.ignore.*;
import android.content.*;
import java.lang.reflect.*;
import java.util.*;
public class IgnoreIntegrationTest {
 public static class Base {protected int currentAccount=0;}
 public static class Controller extends Base {public ArrayList<Object> pushMessages=new ArrayList<>();}
 public static class Message {public long peer;public Message(long id){peer=id;}public long getDialogId(){return peer;}}
 public static class Cell {public float U3=0.2f,V3=0.4f;public int E0=0,R0=9,T0=2,U0=3,V0=1;public boolean S0=true,F3=true,a4=true,b4=true,c4=true;public long getDialogId(){return 456;}}
 public static class Task {public long dialogId;public Task(long id){dialogId=id;}}
 static void check(boolean b,String why){if(!b)throw new AssertionError(why);}
 static boolean failCommit;
 static Map<String,String> data=new HashMap<>();
 static SharedPreferences preferences(){
  return (SharedPreferences)Proxy.newProxyInstance(IgnoreIntegrationTest.class.getClassLoader(),new Class[]{SharedPreferences.class},(p,m,a)->{
   switch(m.getName()){
    case "getString":return data.getOrDefault((String)a[0],(String)a[1]);
    case "getAll":return new HashMap<>(data);
    case "edit":{
     Map<String,String> writes=new HashMap<>();Set<String> removals=new HashSet<>();
     return Proxy.newProxyInstance(IgnoreIntegrationTest.class.getClassLoader(),new Class[]{SharedPreferences.Editor.class},(ep,em,ea)->{
      switch(em.getName()){
       case "putString":writes.put((String)ea[0],(String)ea[1]);return ep;
       case "remove":removals.add((String)ea[0]);return ep;
       case "commit":if(failCommit)return false;for(String key:removals)data.remove(key);data.putAll(writes);return true;
       default:throw new AssertionError(em.getName());
      }
     });
    }
    default:throw new AssertionError(m.getName());
   }
  });
 }
 public static void main(String[] args)throws Exception{
  org.telegram.messenger.ApplicationLoader.prefs=preferences();
  Controller controller=new Controller();long peer=456;
  check(!IgnoreHooks.blockRead(controller,peer),"ordinary reads allowed");
  IgnoreStore.set(0,peer,IgnoreRules.begin(null,50,1000));
  check(IgnoreHooks.blockRead(controller,peer),"hidden history receipt blocked");
  Cell cell=new Cell();int serverUnread=9;check(IgnorePresentation.suppressUnread(cell),"ignored row must suppress counts");
  check(cell.R0==0&&cell.T0==0&&cell.U0==0&&cell.V0==0&&!cell.F3&&!cell.a4&&!cell.b4&&!cell.c4&&!cell.S0,"all unread indicators hidden");
  check(cell.U3==1f&&cell.V3==1f,"old badge animations must finish immediately");
  check(serverUnread==9&&IgnoreHooks.blockRead(controller,peer),"rendering must not mark unread messages read");
  check(IgnoreHooks.blockReadTask(controller,new Task(peer)),"queued read receipt blocked");
  check(!IgnoreHooks.blockRead(controller,789),"other chats unaffected");
  Message secret=new Message(peer),ordinary=new Message(789);ArrayList<Object> messages=new ArrayList<>(Arrays.asList(secret,ordinary));
  check(IgnoreHooks.filterNotifications(controller,messages).equals(Arrays.asList(ordinary)),"ignored notifications suppressed");
  check(messages.size()==2,"message storage must remain intact");
  controller.pushMessages.addAll(messages);check(IgnoreHooks.filterNotificationState(controller),"cached notification filtering");
  check(controller.pushMessages.equals(Arrays.asList(ordinary)),"old notifications removed");
  IgnoreRules.Entry hidden=IgnoreStore.get(0,peer);IgnoreStore.set(0,peer,hidden.preview());
  check(!IgnoreStore.get(0,peer).hides(51,1001),"preview reveals pending messages");
  check(IgnoreHooks.blockRead(controller,peer),"preview never marks read");
  cell.R0=7;cell.F3=true;check(IgnorePresentation.suppressUnread(cell)&&cell.R0==0&&!cell.F3,"preview also suppresses unread badges");
  IgnoreStore.set(0,peer,IgnoreStore.get(0,peer).cancel());
  check(IgnoreStore.get(0,peer).hides(51,1001),"cancel restores original boundary");
  check(IgnoreStore.get(0,peer).boundaryId==50,"cancel does not advance boundary");
  IgnoreStore.set(0,peer,hidden.preview());
  Field previews=IgnoreStore.class.getDeclaredField("previews");previews.setAccessible(true);((Map<?,?>)previews.get(null)).clear();
  check(IgnoreStore.get(0,peer).mode==IgnoreRules.HIDDEN,"restart exits preview but keeps ignore");
  org.telegram.messenger.UserConfig.owner=124;check(!IgnoreStore.active(0,peer),"account slot reuse isolated");org.telegram.messenger.UserConfig.owner=123;
  failCommit=true;try{IgnoreStore.set(0,peer,hidden.confirm());throw new AssertionError("failed write accepted");}catch(java.io.IOException expected){}
  check(IgnoreHooks.blockRead(controller,peer),"write failure keeps reads blocked");failCommit=false;
  IgnoreStore.set(0,peer,hidden.confirm());check(!IgnoreHooks.blockRead(controller,peer),"explicit confirmation permits reads");
  cell.R0=9;check(!IgnorePresentation.suppressUnread(cell)&&cell.R0==9,"ordinary row counts restored after confirmation");
  check(IgnoreHooks.filterNotifications(controller,messages).size()==2,"notifications restored after confirmation");
  IgnoreStore.set(0,peer,IgnoreRules.begin(null,75,2000));
  failCommit=true;try{IgnoreStore.set(0,peer,IgnoreStore.get(0,peer).confirm());throw new AssertionError("failed direct stop accepted");}catch(java.io.IOException expected){}
  check(IgnoreHooks.blockRead(controller,peer),"failed direct stop keeps ignore active");failCommit=false;
  IgnoreStore.set(0,peer,IgnoreStore.get(0,peer).confirm());
  check(!IgnoreStore.active(0,peer)&&!IgnoreHooks.blockRead(controller,peer),"stop exits hidden directly without preview");
  System.out.println("PASS actual Android ignore store/hooks: account isolation, queued receipts, notifications, private preview, cancellation, restart and failed writes");
 }
}