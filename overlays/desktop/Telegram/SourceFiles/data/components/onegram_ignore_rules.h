#pragma once

namespace Data::OneGram {

enum class IgnoreMode { Off, Hidden, Preview };

struct IgnoreEntry {
	IgnoreMode mode = IgnoreMode::Off;
	long long boundaryId = 0;
	long long since = 0;

	[[nodiscard]] constexpr bool active() const {
		return mode != IgnoreMode::Off;
	}
	[[nodiscard]] constexpr bool blocksRead() const {
		return active();
	}
	[[nodiscard]] constexpr bool blocksSend() const {
		return active();
	}
	[[nodiscard]] constexpr bool hides(long long id, long long date) const {
		return mode == IgnoreMode::Hidden
			&& (boundaryId > 0 ? id > boundaryId : date >= since);
	}
	[[nodiscard]] constexpr IgnoreEntry preview() const {
		return active() ? IgnoreEntry{ IgnoreMode::Preview, boundaryId, since } : *this;
	}
	[[nodiscard]] constexpr IgnoreEntry cancel() const {
		return active() ? IgnoreEntry{ IgnoreMode::Hidden, boundaryId, since } : *this;
	}
	[[nodiscard]] constexpr IgnoreEntry confirm() const {
		return { IgnoreMode::Off, boundaryId, since };
	}
};

[[nodiscard]] constexpr IgnoreEntry BeginIgnore(
		IgnoreEntry existing,
		long long boundaryId,
		long long since) {
	return existing.active()
		? existing
		: IgnoreEntry{ IgnoreMode::Hidden, boundaryId > 0 ? boundaryId : 0, since };
}

}  
