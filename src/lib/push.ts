// Web Push client helpers (design §1-⑤, §7 iOS onboarding).

export function isIOS(): boolean {
  return /iPad|iPhone|iPod/.test(navigator.userAgent);
}

export function isStandalone(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as unknown as { standalone?: boolean }).standalone === true
  );
}

export function pushSupported(): boolean {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export type PushSubscriptionJSONSafe = {
  endpoint: string;
  keys: { p256dh: string; auth: string };
};

/** Register the SW, ask permission, and return a push subscription. Throws with
 *  a user-facing Korean message on each failure mode. */
export async function ensurePushSubscription(): Promise<PushSubscriptionJSONSafe> {
  if (!pushSupported()) {
    throw new Error(
      isIOS()
        ? "iPhone에서는 먼저 공유 버튼 → '홈 화면에 추가' 후, 홈 화면 아이콘으로 열어야 알림을 받을 수 있습니다."
        : "이 브라우저는 웹 푸시를 지원하지 않습니다."
    );
  }
  const reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("알림 권한이 거부되었습니다. 브라우저 설정에서 허용해 주세요.");
  }

  const key = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;
  if (!key) throw new Error("서버에 VAPID 공개키가 설정되지 않았습니다.");

  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(key) as BufferSource,
    }));

  const json = sub.toJSON();
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
    throw new Error("푸시 구독 생성에 실패했습니다.");
  }
  return { endpoint: json.endpoint, keys: { p256dh: json.keys.p256dh, auth: json.keys.auth } };
}
