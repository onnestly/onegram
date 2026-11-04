#pragma once
#include "settings/settings_type.h"
#include <QtCore/QString>
class QWidget;
class PeerData;
namespace Window { class SessionController; }
namespace Ui::OneGram {
QString Text(const char *ru, const char *en);
::Settings::Type SettingsId();
void Settings(not_null<Window::SessionController*> controller);
void IgnoredChats(not_null<Window::SessionController*> controller);
void AttachIgnoreBar(QWidget *parent, not_null<Window::SessionController*> controller,
    Fn<PeerData*()> peer, Fn<void()> refreshNativeControls);
}
