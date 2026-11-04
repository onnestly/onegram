from pathlib import Path
import re
OWNER = 'Lorg/onegram/ignore/IgnoreHooks;'

def patch_method(path, signature, code, marker):
    source = path.read_text(encoding='utf-8')
    pattern = '(?m)(^\\.method[^\\n]* ' + re.escape(signature) + '\\n)(.*?)^\\.end method'
    match = re.search(pattern, source, re.S)
    if not match:
        raise RuntimeError('Required privacy hook is missing: ' + signature)
    body = match[2]
    if marker in body:
        return
    declaration = re.search('(?m)^    \\.locals (\\d+)\\n', body)
    if not declaration or (int(declaration[1]) < 1 and re.search('\\bv0\\b', code)):
        raise RuntimeError('Unsupported registers for privacy hook: ' + signature)
    body = body[:declaration.end()] + '\n' + code + '\n' + body[declaration.end():]
    source = source[:match.start(2)] + body + source[match.end(2):]
    path.write_text(source, encoding='utf-8')

def wrap_cell(path, visibility, accessibility):
    source = path.read_text(encoding='utf-8')
    owner = re.search('(?m)^\\.class[^\\n]* (L[^;]+;)', source)[1]
    parent = re.search('(?m)^\\.super (L[^;]+;)', source)[1]
    for name, arguments in [('onMeasure', 'II'), ('onDraw', 'Landroid/graphics/Canvas;')]:
        original = 'onegramIgnoreOriginal' + name
        if original in source:
            continue
        pattern = '(?m)^\\.method[^\\n]* ' + name + '\\(' + re.escape(arguments) + '\\)V$'
        if not re.search(pattern, source):
            raise RuntimeError('Missing privacy view hook: ' + str(path) + ' ' + name)
        source = re.sub(pattern, '.method private ' + original + '(' + arguments + ')V', source, count=1)
        if name == 'onMeasure':
            body = f'    .locals 3\n    invoke-static/range {{p0 .. p0}}, {OWNER}->{visibility}(Landroid/view/View;)Z\n    move-result v0\n    if-eqz v0, :onegram_visible\n    invoke-static {{p1}}, Landroid/view/View$MeasureSpec;->getSize(I)I\n    move-result v1\n    const/4 v2, 0x0\n    invoke-virtual {{p0, v1, v2}}, Landroid/view/View;->setMeasuredDimension(II)V\n    return-void\n    :onegram_visible\n    invoke-direct {{p0, p1, p2}}, {owner}->{original}(II)V\n    return-void\n'
        else:
            body = f'    .locals 1\n    invoke-static/range {{p0 .. p0}}, {OWNER}->{visibility}(Landroid/view/View;)Z\n    move-result v0\n    if-eqz v0, :onegram_visible\n    return-void\n    :onegram_visible\n    invoke-direct {{p0, p1}}, {owner}->{original}(Landroid/graphics/Canvas;)V\n    return-void\n'
        source += '\n.method public ' + name + '(' + arguments + ')V\n' + body + '.end method\n'
    method = 'onInitializeAccessibilityNodeInfo(Landroid/view/accessibility/AccessibilityNodeInfo;)V'
    original = 'onegramIgnoreOriginalAccessibility'
    if OWNER + '->' + accessibility not in source:
        pattern = '(?m)^\\.method[^\\n]* ' + re.escape(method) + '$'
        exists = bool(re.search(pattern, source))
        if exists:
            source = re.sub(pattern, '.method private ' + original + '(Landroid/view/accessibility/AccessibilityNodeInfo;)V', source, count=1)
        call = 'invoke-direct {p0, p1}, ' + owner + '->' + original if exists else 'invoke-super {p0, p1}, ' + parent + '->onInitializeAccessibilityNodeInfo'
        source += f'\n.method public {method}\n    .locals 0\n    {call}(Landroid/view/accessibility/AccessibilityNodeInfo;)V\n    invoke-static/range {{p0 .. p1}}, {OWNER}->{accessibility}(Landroid/view/View;Landroid/view/accessibility/AccessibilityNodeInfo;)V\n    return-void\n.end method\n'
    path.write_text(source, encoding='utf-8')

def patch_ignore_sources(decoded: Path):
    controller = next(decoded.glob('smali*/org/telegram/messenger/MessagesController.smali'))
    guards = [('markAllTopicsAsRead(J)V', 'blockRead(Ljava/lang/Object;J)Z', 'p0 .. p2'), ('markDialogAsRead(JIIIZJIZI)V', 'blockRead(Ljava/lang/Object;J)Z', 'p0 .. p2'), ('markDialogAsReadNow(JJ)V', 'blockRead(Ljava/lang/Object;J)Z', 'p0 .. p2'), ('markMentionsAsRead(JJ)V', 'blockRead(Ljava/lang/Object;J)Z', 'p0 .. p2'), ('markReactionsAsRead(JJ)V', 'blockRead(Ljava/lang/Object;J)Z', 'p0 .. p2'), ('markPollVotesAsRead(JJ)V', 'blockRead(Ljava/lang/Object;J)Z', 'p0 .. p2'), ('markMessageAsRead(JJI)V', 'blockRead(Ljava/lang/Object;J)Z', 'p0 .. p2'), ('markMessageAsRead2(JILorg/telegram/tgnet/TLRPC$InputChannel;IJZ)V', 'blockRead(Ljava/lang/Object;J)Z', 'p0 .. p2'), ('markMentionMessageAsRead(IJJ)V', 'blockMention(Ljava/lang/Object;IJJ)Z', 'p0 .. p5'), ('markMessageContentAsRead(Lorg/telegram/messenger/MessageObject;)V', 'blockReadMessage(Ljava/lang/Object;Ljava/lang/Object;)Z', 'p0 .. p1'), ('completeReadTask(Lorg/telegram/messenger/MessagesController$ReadTask;)V', 'blockReadTask(Ljava/lang/Object;Ljava/lang/Object;)Z', 'p0 .. p1')]
    for signature, method, registers in guards:
        code = f'    invoke-static/range {{{registers}}}, {OWNER}->{method}\n    move-result v0\n    if-eqz v0, :onegram_ignore_allow_read\n    return-void\n    :onegram_ignore_allow_read\n'
        patch_method(controller, signature, code, OWNER + '->' + method)
    notifications = next(decoded.glob('smali*/org/telegram/messenger/NotificationsController.smali'))
    patch_method(notifications, 'processNewMessages(Ljava/util/ArrayList;ZZLjava/util/concurrent/CountDownLatch;)V', f'    invoke-static/range {{p0 .. p1}}, {OWNER}->filterNotifications(Ljava/lang/Object;Ljava/util/ArrayList;)Ljava/util/ArrayList;\n    move-result-object p1\n', OWNER + '->filterNotifications')
    patch_method(notifications, 'showOrUpdateNotification(Z)V', f'    invoke-static/range {{p0 .. p0}}, {OWNER}->filterNotificationState(Ljava/lang/Object;)Z\n    move-result v0\n    if-nez v0, :onegram_ignore_notifications_ready\n    return-void\n    :onegram_ignore_notifications_ready\n', OWNER + '->filterNotificationState')
    sender = next(decoded.glob('smali*/org/telegram/messenger/SendMessagesHelper.smali'))
    patch_method(sender, 'sendMessage(Lorg/telegram/messenger/SendMessagesHelper$SendMessageParams;)V', f'    invoke-static/range {{p0 .. p1}}, {OWNER}->blockSend(Ljava/lang/Object;Ljava/lang/Object;)Z\n    move-result v0\n    if-eqz v0, :onegram_send_allowed\n    return-void\n    :onegram_send_allowed\n', OWNER + '->blockSend(')
    patch_method(sender, 'sendMessage(Ljava/util/ArrayList;JZZZIILorg/telegram/messenger/MessageObject;IJJLorg/telegram/messenger/MessageSuggestionParams;)I', f'    invoke-static/range {{p0 .. p3}}, {OWNER}->blockForward(Ljava/lang/Object;Ljava/lang/Object;J)Z\n    move-result v0\n    if-eqz v0, :onegram_send_allowed\n    const/4 v0, 0x0\n    return v0\n    :onegram_send_allowed\n', OWNER + '->blockForward(')
    for signature in ('sendTyping(JJII)Z', 'sendTyping(JJILjava/lang/String;I)Z'):
        patch_method(controller, signature, f'    invoke-static/range {{p0 .. p2}}, {OWNER}->blockRead(Ljava/lang/Object;J)Z\n    move-result v0\n    if-eqz v0, :onegram_typing_allowed\n    const/4 v0, 0x0\n    return v0\n    :onegram_typing_allowed\n', OWNER + '->blockRead(')
    image = next(decoded.glob('smali*/org/telegram/messenger/ImageReceiver.smali'))
    patch_method(image, 'draw(Landroid/graphics/Canvas;)Z', f'    invoke-static/range {{p0 .. p0}}, {OWNER}->hideThumbnail(Ljava/lang/Object;)Z\n    move-result v0\n    if-eqz v0, :onegram_image_allowed\n    const/4 v0, 0x0\n    return v0\n    :onegram_image_allowed\n', OWNER + '->hideThumbnail')
    for name in ('u1', 'x0', 'f2', 'u7', 'z'):
        wrap_cell(next(decoded.glob('smali*/org/telegram/ui/Cells/' + name + '.smali')), 'hideMessageCell', 'messageAccessibility')
    dialog = next(decoded.glob('smali*/org/telegram/ui/Cells/s2.smali'))
    wrap_cell(dialog, 'hideDialogCell', 'dialogAccessibility')
    patch_method(dialog, 'onTouchEvent(Landroid/view/MotionEvent;)Z', '    invoke-static/range {p0 .. p1}, Lorg/onegram/OneGramUi;->rememberDialogTouch(Landroid/view/View;Landroid/view/MotionEvent;)V\n', 'OneGramUi;->rememberDialogTouch')
    fragment = next(decoded.glob('smali*/org/telegram/ui/ActionBar/r2.smali'))
    patch_method(fragment, 'onResume()V', '    invoke-static/range {p0 .. p0}, Lorg/onegram/OneGramUi;->trackFragment(Ljava/lang/Object;)V\n', 'OneGramUi;->trackFragment')
    popup = next(decoded.glob('smali*/org/telegram/ui/ActionBar/r1.smali'))
    for signature in ('showAsDropDown(Landroid/view/View;II)V', 'showAtLocation(Landroid/view/View;III)V'):
        patch_method(popup, signature, '    invoke-static/range {p0 .. p0}, Lorg/onegram/OneGramUi;->decorateMenu(Landroid/widget/PopupWindow;)V\n', 'OneGramUi;->decorateMenu')
