export interface Alarm {
  id: string;
  name: string;
  enabled: boolean;
  time: string;
  repeat: "once" | "weekly";
  weekdays: number[];
  date: string | null;
  skip_next: boolean;
  media_player: string;
  source_uri: string;
  source_kind: "music_assistant" | "media_player";
  volume: number;
  fade_seconds: number;
  /** Restore what the speaker was playing when the alarm ends. MA sources only. */
  resume_previous: boolean;
  snooze_minutes: number;
  auto_dismiss_minutes: number;
  pre_alarm_minutes: number;
  pre_alarm_script: string | null;
  /** notify.* entities to push a Dismiss/Snooze-actionable alert to on ring. */
  notify_targets: string[];
  /** The Home Assistant user this alarm belongs to. null means unowned. */
  owner_id: string | null;
  next_fire: string | null;
  is_ringing: boolean;
  is_snoozed: boolean;
}

export interface Snapshot {
  alarms: Alarm[];
  ringing: string[];
  snoozed: string[];
  user_id: string | null;
  is_admin: boolean;
  /** null means unrestricted; [] means an admin has granted nothing yet. */
  allowed_media_players: string[] | null;
}

export interface WakeyUser {
  id: string;
  name: string;
  is_admin: boolean;
  is_owner: boolean;
}

export interface UserPolicy {
  user_id: string;
  allowed_media_players: string[];
}

export interface OrphanedAlarm {
  id: string;
  name: string;
  media_player: string;
}

/** Only the bits of the HA object this panel actually touches. */
export interface HomeAssistant {
  states: Record<string, { state: string; attributes: Record<string, unknown> }>;
  locale: unknown;
  themes: unknown;
  language: string;
  user?: { id: string; name: string; is_admin: boolean };
  callWS<T>(msg: Record<string, unknown>): Promise<T>;
  connection: {
    subscribeMessage<T>(
      cb: (msg: T) => void,
      msg: Record<string, unknown>
    ): Promise<() => void>;
  };
}

export const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export const emptyDraft = (): Partial<Alarm> => ({
  name: "Alarm",
  time: "07:00",
  repeat: "weekly",
  weekdays: [0, 1, 2, 3, 4],
  media_player: "",
  source_uri: "",
  source_kind: "music_assistant",
  volume: 0.7,
  fade_seconds: 0,
  snooze_minutes: 9,
  auto_dismiss_minutes: 30,
  enabled: true,
  notify_targets: [],
  resume_previous: false,
});

/**
 * Nudge Home Assistant into defining its lazily-loaded form elements.
 *
 * ha-form and the selector elements live in the frontend's editor bundle,
 * which is only pulled in on demand. loadCardHelpers is the documented hook
 * that forces it. Everything here is best-effort: if it fails the panel falls
 * back to plain inputs rather than rendering nothing.
 */
export async function ensureHaForm(): Promise<boolean> {
  try {
    const helpers = await (window as any).loadCardHelpers?.();
    const card = await helpers?.createCardElement({ type: "entities", entities: [] });
    await (card?.constructor as any)?.getConfigElement?.();
  } catch {
    /* non-fatal */
  }
  return Promise.race([
    customElements.whenDefined("ha-form").then(() => true),
    new Promise<boolean>((r) => setTimeout(() => r(false), 4000)),
  ]);
}
