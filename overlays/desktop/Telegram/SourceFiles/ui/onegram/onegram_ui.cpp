#include "ui/onegram/onegram_ignore_layout.h"
#include "settings/settings_common_session.h"
#include "settings/settings_common.h"
#include "ui/vertical_list.h"
#include "ui/wrap/vertical_layout.h"
#include "ui/widgets/buttons.h"
#include "ui/widgets/labels.h"
#include "styles/style_settings.h"
#include "styles/style_chat.h"
#include "styles/style_chat_helpers.h"
#include "styles/style_menu_icons.h"
#include "boxes/peer_list_box.h"
#include "history/history_item.h"
#include "ui/onegram/onegram_ui.h"
#include "data/components/onegram_features.h"
#include "data/data_peer.h"
#include "data/data_session.h"
#include "history/history.h"
#include "main/main_session.h"
#include "window/window_session_controller.h"
#include "lang/lang_instance.h"
#include "core/application.h"
#include "core/core_settings.h"
#include "storage/localstorage.h"
#include "apiwrap.h"
#include "mtproto/mtp_instance.h"
#include <QtWidgets/QApplication>
#include <QtCore/QSettings>
#include <QtCore/QDir>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QSaveFile>
#include <QtCore/QTimer>
#include <QtCore/QPointer>
#include <QtCore/QRegularExpression>

namespace Ui::OneGram {
namespace {
QString ProfileFile(const QString &name) { return QDir(cWorkingDir()).absoluteFilePath(u"../"_q + name); }
QJsonObject ReadJson(const QString &path) {
    QFile file(path);
    return file.open(QIODevice::ReadOnly) ? QJsonDocument::fromJson(file.readAll()).object() : QJsonObject();
}
bool ProxyEnabled() { return ReadJson(ProfileFile(u"onegram-preferences.json"_q)).value(u"proxy_enabled"_q).toBool(true); }
bool SetProxy(bool enabled) {
    const auto path = ProfileFile(u"onegram-preferences.json"_q);
    auto prefs = ReadJson(path);
    prefs.insert(u"proxy_enabled"_q, enabled);
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly) || file.write(QJsonDocument(prefs).toJson()) < 0 || !file.commit()) return false;
    const auto apply = [=] {
        if (ProxyEnabled() != enabled) return;
        auto proxy = Core::App().settings().proxy().selected();
        if (enabled) {
            const auto config = ReadJson(ProfileFile(u"onegram.json"_q));
            proxy.type = MTP::ProxyData::Type::Mtproto;
            proxy.host = u"127.0.0.1"_q;
            proxy.port = config.value(u"port"_q).toInt();
            proxy.password = u"dd"_q + config.value(u"secret"_q).toString();
            if (!proxy.port || proxy.password.size() != 34) return;
        }
        Core::App().setCurrentProxy(proxy, enabled ? MTP::ProxyData::Settings::Enabled : MTP::ProxyData::Settings::Disabled);
        Local::writeSettings();
    };
    apply();
    if (enabled) QTimer::singleShot(1500, QCoreApplication::instance(), apply);
    return true;
}
std::map<::Ui::SettingsButton*, std::shared_ptr<rpl::event_stream<QString>>> ButtonTextChanges;
void SetButtonText(::Ui::SettingsButton *button, QString text) {
    if (const auto i = ButtonTextChanges.find(button); i != ButtonTextChanges.end()) i->second->fire(std::move(text));
}
void Updates(not_null<Window::SessionController*> controller) {
    controller->session().api().request(MTPcontacts_ResolveUsername(MTP_flags(0), MTP_string(u"On3Gram"_q), MTP_string()))
    .done(crl::guard(controller, [=](const MTPcontacts_ResolvedPeer &result) {
        const auto &data = result.data();
        controller->session().data().processUsers(data.vusers());
        controller->session().data().processChats(data.vchats());
        controller->showPeerHistory(peerFromMTP(data.vpeer()));
    })).send();
}
void CheckVersion(not_null<Window::SessionController*> controller, QPointer<::Ui::SettingsButton> button) {
    SetButtonText(button, Text("Проверка…", "Checking…"));
    button->setEnabled(false);
    const auto done = std::make_shared<bool>(false);
    const auto failed = [=] {
        if (*done) return;
        *done = true;
        if (button) { SetButtonText(button, Text("Версия 1.0.3 — Не удалось проверить. Повторить", "Version 1.0.3 — Check failed. Retry")); button->setEnabled(true); }
    };
    QTimer::singleShot(20000, button, failed);
    auto &session = controller->session();
    session.api().request(MTPcontacts_ResolveUsername(MTP_flags(0), MTP_string(u"On3Gram"_q), MTP_string()))
    .done(crl::guard(controller, [=](const MTPcontacts_ResolvedPeer &result) {
        if (*done || !button) return;
        const auto &data = result.data();
        auto &session = controller->session();
        session.data().processUsers(data.vusers());
        session.data().processChats(data.vchats());
        const auto peer = session.data().peerLoaded(peerFromMTP(data.vpeer()));
        if (!peer) { failed(); return; }
        session.api().request(MTPmessages_GetHistory(peer->input(), MTP_int(0), MTP_int(0), MTP_int(0), MTP_int(50), MTP_int(0), MTP_int(0), MTP_long(0)))
        .done(crl::guard(controller, [=](const MTPmessages_Messages &messages) {
            if (*done || !button) return;
            auto found = false;
            auto newer = false;
            const auto scan = [&](const auto &data) {
                if constexpr (requires { data.vmessages(); }) {
                    for (const auto &message : data.vmessages().v) {
                        message.match([&](const MTPDmessage &m) {
                            const auto text = qs(m.vmessage());
                            if (text.contains(u"Android"_q, Qt::CaseInsensitive) && !text.contains(u"Windows"_q, Qt::CaseInsensitive)) return;
                            const auto re = QRegularExpression(u"OneGram(?:[- \\t]+(?:Windows|x64|Desktop))*[- \\t:vV]*(\\d+)\\.(\\d+)\\.(\\d+)"_q, QRegularExpression::CaseInsensitiveOption);
                            auto matches = re.globalMatch(text);
                            while (matches.hasNext()) {
                                const auto m = matches.next();
                                found = true;
                                const auto version = std::array<int, 3>{ m.captured(1).toInt(), m.captured(2).toInt(), m.captured(3).toInt() };
                                newer |= version > std::array<int, 3>{1, 0, 3};
                            }
                        }, [](const auto &) {});
                    }
                }
            };
            messages.match(scan);
            if (!found) { failed(); return; }
            *done = true;
            button->setEnabled(true);
            SetButtonText(button, newer ? Text("Версия 1.0.3 — Обновить", "Version 1.0.3 — Update") : Text("Версия 1.0.3 ✓", "Version 1.0.3 ✓"));
            button->setProperty("onegramUpdateAvailable", newer);
        })).fail([=](const MTP::Error &) { failed(); }).send();
    })).fail([=](const MTP::Error &) { failed(); }).send();
}
}  

QString Text(const char *ru, const char *en) {
    const auto russian = Lang::GetInstance().cloudLangCode(Lang::Pack::Current).startsWith(u"ru"_q)
        || Lang::GetInstance().id().startsWith(u"ru"_q);
    return QString::fromUtf8(russian ? ru : en);
}

namespace {
class OneGramSection final : public ::Settings::Section<OneGramSection> {
public:
    OneGramSection(QWidget *parent, not_null<Window::SessionController*> window)
    : Section(parent, window) {
        const auto content = ::Ui::CreateChild<::Ui::VerticalLayout>(this);
        const auto heading = [&](const QString &text) {
            ::Ui::AddSkip(content);
            ::Ui::AddSubsectionTitle(content, rpl::single(text));
        };
        const auto action = [&](rpl::producer<QString> text, Fn<void()> callback) {
            const auto changes = std::make_shared<rpl::event_stream<QString>>();
            const auto button = ::Settings::AddButtonWithIcon(content, rpl::merge(std::move(text), changes->events()), st::settingsButtonNoIcon);
            ButtonTextChanges.emplace(button.get(), changes);
            QObject::connect(button, &QObject::destroyed, [key = button.get()] { ButtonTextChanges.erase(key); });
            button->setClickedCallback(std::move(callback));
            return button;
        };
        const auto toggle = [&](const QString &text, bool checked, Fn<bool(bool)> save) {
            const auto button = ::Settings::AddButtonWithIcon(content, rpl::single(text), st::settingsButtonNoIcon);
            button->toggleOn(rpl::single(checked));
            button->toggledChanges() | rpl::on_next([=](bool enabled) {
                if (!save(enabled)) {
                    button->toggleOn(rpl::single(!enabled));
                    window->showToast(Text("Не удалось сохранить настройки", "Could not save settings"));
                }
            }, content->lifetime());
        };
        heading(Text("Прокси", "Proxy"));
        toggle(Text("Встроенный прокси", "Built-in proxy"), ProxyEnabled(), SetProxy);
        const auto check = action(rpl::single(Text("Проверить подключение", "Check connection")), [] {});
        check->setClickedCallback([=] {
            if (!ProxyEnabled() || !Core::App().settings().proxy().isEnabled()) {
                SetButtonText(check, Text("Прокси выключен", "Proxy is off")); return;
            }
            SetButtonText(check, Text("Проверка…", "Checking…")); check->setEnabled(false);
            const auto weak = QPointer<::Ui::SettingsButton>(check.get());
            const auto done = std::make_shared<bool>(false);
            const auto finish = [=](bool ok) {
                if (*done) return; *done = true;
                if (weak) { weak->setEnabled(true); SetButtonText(weak, ok
                    ? Text("Прокси работает ✓", "Proxy works ✓")
                    : Text("Нет ответа. Проверить снова", "No response. Retry")); }
            };
            const auto request = window->session().api().request(MTPhelp_GetNearestDc())
                .done([=](const MTPNearestDc &) { finish(ProxyEnabled() && Core::App().settings().proxy().isEnabled()); })
                .fail([=](const MTP::Error &) { finish(false); }).send();
            QTimer::singleShot(15000, check.get(), [=] {
                if (!*done) { window->session().api().request(request).cancel(); finish(false); }
            });
        });
        ::Ui::AddDividerText(content, rpl::single(Text("Прокси работает в фоне вместе с OneGram.", "The built-in proxy runs in the background with OneGram.")));
        const auto session = &window->session();
        heading(Text("Игнорирование", "Ignore"));
        toggle(Text("Убирать из списка чатов", "Hide from chat list"), Data::OneGram::HideIgnoredChats(session), [=](bool on) {
            return Data::OneGram::SetHideIgnoredChats(session, on);
        });
        action(rpl::single(Text("Чаты в игноре", "Ignored Chats")), [=] { IgnoredChats(window); });
        ::Ui::AddDividerText(content, rpl::single(Text("Скрытые чаты: ☰ → Чаты в игноре, под Избранным.", "Hidden chats: ☰ → Ignored Chats, below Saved Messages.")));
        heading(Text("Огоньки", "Streaks"));
        toggle(Text("Показывать огоньки", "Show streaks"), Data::OneGram::StreaksEnabled(session), [=](bool on) {
            return Data::OneGram::SetStreaksEnabled(session, on);
        });
        action(rpl::single(Text("Обновить огоньки", "Recalculate streaks")), [=] {
            Data::OneGram::RefreshStreaks(session);
            window->showToast(Text("Пересчёт огоньков начат", "Recalculating streaks"));
        });
        ::Ui::AddDivider(content);
        heading(Text("Обновления", "Updates"));
        const auto version = action(rpl::single(Text("Версия 1.0.3 — Проверить", "Version 1.0.3 — Check")), [] {});
        version->setClickedCallback([=] {
            if (version->property("onegramUpdateAvailable").toBool()) Updates(window);
            else CheckVersion(window, version.get());
        });
        ::Ui::AddSkip(content);
        ::Ui::ResizeFitChild(this, content);
    }
    rpl::producer<QString> title() override { return rpl::single(Text("Настройки OneGram", "OneGram Settings")); }
};
}
::Settings::Type SettingsId() { return OneGramSection::Id(); }
void Settings(not_null<Window::SessionController*> controller) { controller->showSettings(SettingsId()); }

namespace {
class IgnoredListController final : public PeerListController {
public:
    explicit IgnoredListController(not_null<Window::SessionController*> controller) : _controller(controller) {}
    Main::Session &session() const override { return _controller->session(); }
    void prepare() override {
        delegate()->peerListSetTitle(rpl::single(Text("Чаты в игноре", "Ignored Chats")));
        for (const auto id : Data::OneGram::IgnoredChats(&session())) {
            const auto peer = session().data().peer(id);
            auto row = std::make_unique<PeerListRow>(peer);
            const auto boundary = MsgId(Data::OneGram::IgnoreFor(peer).boundaryId);
            const auto item = session().data().message(id, boundary);
            row->setCustomStatus(item ? item->notificationText().text : QString());
            delegate()->peerListAppendRow(std::move(row));
        }
        delegate()->peerListRefreshRows();
    }
    void rowClicked(not_null<PeerListRow*> row) override {
        const auto controller = _controller;
        const auto peer = row->peer();
        controller->hideLayer();
        controller->showPeerHistory(peer);
    }
private:
    not_null<Window::SessionController*> _controller;
};
}
void IgnoredChats(not_null<Window::SessionController*> controller) {
    controller->show(Box<PeerListBox>(std::make_unique<IgnoredListController>(controller), [](not_null<PeerListBox*> box) {
        box->addButton(rpl::single(Text("Закрыть", "Close")), [=] { box->closeBox(); });
    }));
}

namespace {
class IgnoreBar final : public ::Ui::RpWidget {
public:
    IgnoreBar(QWidget *parent, Window::SessionController *controller, Fn<PeerData*()> peer, Fn<void()> refresh)
    : ::Ui::RpWidget(parent), _peer(std::move(peer)), _refresh(std::move(refresh)) {
        _stop = new ::Ui::FlatButton(this, Text("Перестать игнорировать", "Stop ignoring"), st::historyUnblock);
        _stop->setObjectName(u"onegram-ignore-stop"_q);
        _stop->setClickedCallback([=] {
            if (const auto peer = _peer()) {
                if (!Data::OneGram::ConfirmIgnore(peer)) controller->showToast(Text("Не удалось сохранить настройки", "Could not save settings"));
            }
            updateState();
        });
        parent->installEventFilter(this);
        const auto timer = new QTimer(this);
        QObject::connect(timer, &QTimer::timeout, this, [=] { updateState(); }); timer->start(200);
        Data::OneGram::FeatureChanges(&controller->session()) | rpl::on_next([=] {
            _refresh();
            updateState();
        }, lifetime());
        updateState();
    }
protected:
    void paintEvent(QPaintEvent *) override {
        auto p = QPainter(this);
        p.fillRect(rect(), st::historyUnblock.bgColor->c);
    }
    bool eventFilter(QObject *watched, QEvent *event) override {
        if (watched == parentWidget() && (event->type() == QEvent::Resize || event->type() == QEvent::Show)) {
            QTimer::singleShot(0, this, [=] { updateState(); });
        }
        return ::Ui::RpWidget::eventFilter(watched, event);
    }
private:
    void updateState() {
        const auto peer = _peer();
        const auto mode = peer ? Data::OneGram::IgnoreFor(peer).mode : Data::OneGram::IgnoreMode::Off;
        const auto parent = parentWidget();
        ApplyIgnoreActionLayout(this, _stop, mode, parent->width(), parent->height(), st::historyUnblock.height);
    }
    Fn<PeerData*()> _peer;
    Fn<void()> _refresh;
    ::Ui::FlatButton *_stop = nullptr;
};
}
void AttachIgnoreBar(QWidget *parent, not_null<Window::SessionController*> controller, Fn<PeerData*()> peer, Fn<void()> refresh) {
    new IgnoreBar(parent, controller, std::move(peer), std::move(refresh));
}
}  
