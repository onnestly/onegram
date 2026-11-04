package org.onegram.ignore;
 
public final class IgnorePresentation {
    public static boolean suppressUnread(Object cell)throws Exception {
        long dialog=((Number)cell.getClass().getMethod("getDialogId").invoke(cell)).longValue();
        int account=((Number)IgnoreStore.field(cell,"E0")).intValue();
        if(!IgnoreStore.active(account,dialog))return false;
        for(String name:new String[]{"R0","T0","U0","V0"})IgnoreStore.findField(cell,name).setInt(cell,0);
        for(String name:new String[]{"S0","F3","a4","b4","c4"})IgnoreStore.findField(cell,name).setBoolean(cell,false);
        for(String name:new String[]{"U3","V3"})IgnoreStore.findField(cell,name).setFloat(cell,1f);
        return true;
    }
}
