package org.onegram;

import android.app.Activity;
import android.widget.TextView;
import java.util.*;
import org.onegram.ignore.IgnoreStore;

final class OneGramUpdates {
    private static String l(String ru,String en){return OneGramUi.russian()?ru:en;}
    static void check(Activity activity,int account,TextView button){
        button.setEnabled(false);button.setText(l("Проверка обновлений…","Checking for updates…"));
        try{
            long owner=IgnoreStore.owner(account);Object resolve=TelegramRequests.create("TL_contacts_resolveUsername");resolve.getClass().getField("username").set(resolve,"On3Gram");
            TelegramRequests.send(account,resolve,safe(activity,button,account,(response,error)->{
                if(error!=null||response==null||IgnoreStore.owner(account)!=owner){failed(activity,button,account);return;}
                Object peer=response.getClass().getField("peer").get(response);long id=peer.getClass().getField("channel_id").getLong(peer);
                List<?> chats=(List<?>)response.getClass().getField("chats").get(response);Object channel=null;for(Object chat:chats)if(chat.getClass().getField("id").getLong(chat)==id)channel=chat;
                if(channel==null){failed(activity,button,account);return;}
                Object input=TelegramRequests.create("TL_inputPeerChannel");input.getClass().getField("channel_id").setLong(input,id);input.getClass().getField("access_hash").setLong(input,channel.getClass().getField("access_hash").getLong(channel));
                Object history=TelegramRequests.create("TL_messages_getHistory");history.getClass().getField("peer").set(history,input);history.getClass().getField("limit").setInt(history,50);
                TelegramRequests.send(account,history,safe(activity,button,account,(messages,historyError)->{
                    if(historyError!=null||messages==null||IgnoreStore.owner(account)!=owner){failed(activity,button,account);return;}
                    String newest=null;
                    for(Object message:(List<?>)messages.getClass().getField("messages").get(messages)){
                        String text=String.valueOf(message.getClass().getField("message").get(message));String filename="";
                        try{Object media=message.getClass().getField("media").get(message);Object document=media.getClass().getField("document").get(media);for(Object attribute:(List<?>)document.getClass().getField("attributes").get(document)){try{filename=String.valueOf(attribute.getClass().getField("file_name").get(attribute));}catch(NoSuchFieldException ignored){}}}catch(ReflectiveOperationException|NullPointerException ignored){}
                        if(filename.endsWith(".exe")||filename.toLowerCase(Locale.ROOT).contains("windows")&&!filename.endsWith(".apk"))continue;
                        String version=ReleaseVersion.find(filename);if(version==null)version=ReleaseVersion.find(text);
                        if(version!=null&&(newest==null||ReleaseVersion.compare(version,newest)>0))newest=version;
                    }
                    if(newest==null){failed(activity,button,account);return;}
                    if(activity.isFinishing())return;button.setEnabled(true);
                    if(ReleaseVersion.compare(newest,OneGramConfig.VERSION)>0){button.setText(l("Версия ","Version ")+OneGramConfig.VERSION+" · "+l("Обновить","Update"));button.setOnClickListener(v->OneGramUi.openUpdates(activity));}
                    else{button.setText(l("Версия ","Version ")+OneGramConfig.VERSION+" ✓");button.setOnClickListener(v->check(activity,account,button));}
                }));
            }));
        }catch(Exception error){failed(activity,button,account);}
    }
    private static TelegramRequests.Response safe(Activity activity,TextView button,int account,TelegramRequests.Response next){
        return (result,error)->{try{next.accept(result,error);}catch(Exception failure){android.util.Log.w("OneGram","Cannot read updates channel release metadata",failure);failed(activity,button,account);}};
    }
    private static void failed(Activity activity,TextView button,int account){if(activity.isFinishing())return;button.setEnabled(true);button.setText(l("Версия ","Version ")+OneGramConfig.VERSION+" · "+l("Не удалось проверить","Check failed"));button.setOnClickListener(v->check(activity,account,button));}
}
