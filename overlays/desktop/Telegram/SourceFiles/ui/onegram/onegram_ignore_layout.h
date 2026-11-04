#pragma once
#include "data/components/onegram_ignore_rules.h"
#include <QtWidgets/QWidget>

namespace Ui::OneGram {
 
inline void ApplyIgnoreActionLayout(QWidget *panel, QWidget *action,
        Data::OneGram::IgnoreMode mode, int width, int parentHeight, int height) {
    const auto active = mode != Data::OneGram::IgnoreMode::Off && width >= 2 && parentHeight >= height;
    panel->setGeometry(0, qMax(0, parentHeight - height), width, height);
    action->setGeometry(0, 0, width, height);
    panel->setVisible(active);
    action->setVisible(active);
    if (active) { action->raise(); panel->raise(); }
}
}
