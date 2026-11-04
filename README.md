# OneGram

A modified Telegram client for Windows x64 and Android 8.0+.

## Features

- Built-in proxy: starts and stops with the client.
- Streaks: consecutive days when both participants in a private chat sent at least one message. Available chat history is included. The flame stays gray until both participants send a message today.
- Local ignoring: new messages are hidden, while notifications and read receipts are suppressed. “Stop ignoring” immediately restores normal chat behavior.
- Proxy, ignore, and streak options in OneGram Settings.

Proxy availability depends on your network. Ignoring only applies to the current device: other clients may independently mark messages as read.

## Credits

- [Telegram Desktop contributors](https://github.com/telegramdesktop/tdesktop) — the Windows client base (GPLv3).
- [Telegram for Android / DrKLO and contributors](https://github.com/DrKLO/Telegram) — the Android client base (GPLv2).
- [Flowseal](https://github.com/Flowseal/tg-ws-proxy) — the WebSocket proxy base, tg-ws-proxy (MIT).
- [Square / Block](https://github.com/square) — [OkHttp](https://github.com/square/okhttp) and [Okio](https://github.com/square/okio), used by the Android HTTP/2 transport.
- [JetBrains and Kotlin contributors](https://github.com/JetBrains/kotlin) — the Kotlin standard library and [JetBrains annotations](https://github.com/JetBrains/java-annotations).
- [Android Open Source Project](https://android.googlesource.com/platform/frameworks/support/) — AndroidX annotation and startup libraries.

See [THIRD-PARTY.md](THIRD-PARTY.md) and [Android dependency notices](android-module/licenses/HTTP2-NOTICES.txt) for licenses and attribution details.
