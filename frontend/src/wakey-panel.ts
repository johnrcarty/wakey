import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import {
  DAY_LABELS,
  emptyDraft,
  ensureHaForm,
  type Alarm,
  type HomeAssistant,
  type Snapshot,
} from "./types";
import "./wakey-admin";

const DAY_OPTIONS = DAY_LABELS.map((label, i) => ({ value: String(i), label }));

@customElement("wakey-panel")
export class WakeyPanel extends LitElement {
  // Set as properties by the panel host, not as attributes.
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public narrow = false;

  @state() private _alarms: Alarm[] = [];
  @state() private _isAdmin = false;
  @state() private _allowedPlayers: string[] | null = null;
  @state() private _view: "alarms" | "admin" = "alarms";
  @state() private _loaded = false;
  @state() private _error: string | null = null;
  @state() private _dialogOpen = false;
  @state() private _editing: string | null = null;
  @state() private _draft: Record<string, any> = {};
  @state() private _haForm = false;

  private _unsub?: () => void;
  private _subscribed = false;

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    // The panel host disconnects panels it is not showing, so leaking this
    // subscription would accumulate.
    this._unsub?.();
    this._unsub = undefined;
    this._subscribed = false;
  }

  protected updated(changed: PropertyValues): void {
    if (changed.has("hass") && this.hass && !this._subscribed) {
      this._subscribed = true;
      this._subscribe();
      ensureHaForm().then((ok) => (this._haForm = ok));
    }
  }

  private async _subscribe(): Promise<void> {
    try {
      this._unsub = await this.hass.connection.subscribeMessage<Snapshot>(
        (msg) => {
          this._alarms = msg.alarms ?? [];
          // Trust the server's view of who this is over hass.user: it is the
          // same value the API is actually enforcing with, so the buttons on
          // screen cannot disagree with what the backend will allow.
          this._isAdmin = msg.is_admin === true;
          this._allowedPlayers = msg.allowed_media_players ?? null;
          this._loaded = true;
          this._error = null;
        },
        { type: "wakey/subscribe" }
      );
    } catch (err: any) {
      this._error = err?.message ?? String(err);
      this._loaded = true;
    }
  }

  /**
   * Whether this user has anywhere to point a new alarm.
   *
   * Speakers are deny-by-default, so a household member who has not been
   * granted any cannot usefully create anything yet — and an Add button that
   * always fails is worse than no Add button.
   */
  private get _canCreate(): boolean {
    return this._allowedPlayers === null || this._allowedPlayers.length > 0;
  }

  // --- actions -----------------------------------------------------------

  private async _call(msg: Record<string, unknown>): Promise<void> {
    try {
      await this.hass.callWS(msg);
    } catch (err: any) {
      this._error = err?.message ?? String(err);
    }
  }

  private _toggle(alarm: Alarm) {
    this._call({ type: "wakey/update", alarm_id: alarm.id, enabled: !alarm.enabled });
  }

  private _skip(alarm: Alarm) {
    this._call({ type: "wakey/skip_next", alarm_id: alarm.id, skip: !alarm.skip_next });
  }

  private _delete(alarm: Alarm) {
    if (!confirm(`Delete "${alarm.name}"?`)) return;
    this._call({ type: "wakey/delete", alarm_id: alarm.id });
  }

  private _trigger(alarm: Alarm) {
    this._call({ type: "wakey/trigger", alarm_id: alarm.id });
  }

  // --- dialog ------------------------------------------------------------

  private _openNew() {
    this._editing = null;
    this._draft = { ...emptyDraft(), weekdays: ["0", "1", "2", "3", "4"] };
    this._dialogOpen = true;
  }

  private _openEdit(alarm: Alarm) {
    this._editing = alarm.id;
    this._draft = {
      ...alarm,
      weekdays: (alarm.weekdays ?? []).map(String),
      media: alarm.media_player ? { entity_id: alarm.media_player } : undefined,
    };
    this._dialogOpen = true;
  }

  private _closeDialog() {
    this._dialogOpen = false;
    this._editing = null;
  }

  private _formChanged(ev: CustomEvent) {
    const value = { ...(ev.detail as any).value };

    // The media selector's "Pick media" tile stays inert until it knows which
    // player to browse. Seeding entity_id from the chosen media player is what
    // makes the browse dialog actually open.
    if (value.media_player) {
      const current = value.media?.entity_id;
      if (current !== value.media_player) {
        value.media = { ...(value.media ?? {}), entity_id: value.media_player };
      }
    }
    // A freshly browsed pick wins over whatever was typed.
    if (value.media?.media_content_id && value.media.media_content_id !== this._draft.media?.media_content_id) {
      value.source_uri = value.media.media_content_id;
    }

    this._draft = value;
  }

  private async _save() {
    const d = this._draft;
    if (!d.time || !d.media_player || !d.source_uri) {
      this._error = "Name, time, media player and source are all required.";
      return;
    }
    const payload: Record<string, unknown> = {
      name: d.name || "Alarm",
      time: String(d.time).slice(0, 5),
      repeat: d.repeat ?? "weekly",
      weekdays: (d.weekdays ?? []).map((x: string) => Number(x)),
      date: d.date ?? null,
      media_player: d.media_player,
      source_uri: d.source_uri,
      source_kind: d.source_kind ?? "music_assistant",
      volume: Number(d.volume ?? 0.7),
      fade_seconds: Number(d.fade_seconds ?? 0),
      resume_previous: Boolean(d.resume_previous ?? false),
      snooze_minutes: Number(d.snooze_minutes ?? 9),
      auto_dismiss_minutes: Number(d.auto_dismiss_minutes ?? 30),
      pre_alarm_minutes: Number(d.pre_alarm_minutes ?? 0),
      pre_alarm_script: d.pre_alarm_script || null,
      notify_targets: d.notify_targets ?? [],
    };
    if (this._editing) {
      await this._call({ type: "wakey/update", alarm_id: this._editing, ...payload });
    } else {
      await this._call({ type: "wakey/create", ...payload, enabled: d.enabled ?? true });
    }
    this._closeDialog();
  }

  private _schema() {
    const repeat = this._draft.repeat ?? "weekly";
    return [
      { name: "name", required: true, selector: { text: {} } },
      { name: "time", required: true, selector: { time: {} } },
      {
        name: "repeat",
        required: true,
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "weekly", label: "Weekly" },
              { value: "once", label: "Once" },
            ],
          },
        },
      },
      ...(repeat === "weekly"
        ? [{ name: "weekdays", selector: { select: { multiple: true, options: DAY_OPTIONS } } }]
        : [{ name: "date", selector: { date: {} } }]),
      {
        name: "media_player",
        required: true,
        selector: {
          entity: {
            filter: { domain: "media_player" },
            // Omitted for admins, who are unrestricted. For everyone else
            // this is the whole point: the picker only offers the speakers
            // they were granted, so the refusal never has to happen.
            ...(this._allowedPlayers
              ? { include_entities: this._allowedPlayers }
              : {}),
          },
        },
      },
      { name: "media", selector: { media: {} } },
      { name: "source_uri", required: true, selector: { text: {} } },
      {
        type: "grid",
        schema: [
          { name: "volume", selector: { number: { min: 0, max: 1, step: 0.05, mode: "slider" } } },
          {
            name: "fade_seconds",
            selector: { number: { min: 0, max: 900, step: 15, mode: "box", unit_of_measurement: "s" } },
          },
        ],
      },
      {
        type: "expandable",
        name: "advanced",
        title: "Advanced",
        schema: [
          {
            name: "snooze_minutes",
            selector: { number: { min: 1, max: 120, mode: "box", unit_of_measurement: "min" } },
          },
          {
            name: "auto_dismiss_minutes",
            selector: { number: { min: 1, max: 240, mode: "box", unit_of_measurement: "min" } },
          },
          {
            name: "pre_alarm_minutes",
            selector: { number: { min: 0, max: 240, mode: "box", unit_of_measurement: "min" } },
          },
          {
            name: "pre_alarm_script",
            selector: { entity: { filter: { domain: "script" } } },
          },
          {
            name: "notify_targets",
            selector: { entity: { multiple: true, filter: { domain: "notify" } } },
          },
          { name: "resume_previous", selector: { boolean: {} } },
        ],
      },
    ];
  }

  private _label = (s: any): string =>
    ({
      name: "Name",
      time: "Time",
      repeat: "Repeat",
      weekdays: "Days",
      date: "Date",
      media_player: "Play on",
      media: "Browse for a track",
      source_uri: "Source (URI or search text)",
      volume: "Volume",
      fade_seconds: "Fade in",
      snooze_minutes: "Snooze length",
      auto_dismiss_minutes: "Auto dismiss after",
      pre_alarm_minutes: "Pre-alarm lead time",
      pre_alarm_script: "Pre-alarm script",
      notify_targets: "Notify on ring",
      resume_previous: "Resume previous playback",
      advanced: "Advanced",
    })[s.name as string] ?? s.name;

  // --- render ------------------------------------------------------------

  private _fmtNext(alarm: Alarm): string {
    if (!alarm.enabled) return "Off";
    if (!alarm.next_fire) return "Never";
    const then = new Date(alarm.next_fire);
    const mins = Math.round((then.getTime() - Date.now()) / 60000);
    if (mins < 60) return `in ${Math.max(1, mins)} min`;
    const h = Math.floor(mins / 60);
    if (h < 24) return `in ${h}h ${mins % 60}m`;
    return then.toLocaleDateString(undefined, { weekday: "long" });
  }

  private _renderAlarm(alarm: Alarm) {
    const days =
      alarm.repeat === "once"
        ? alarm.date ?? "Once"
        : alarm.weekdays.length === 7
          ? "Every day"
          : alarm.weekdays.length === 0
            ? "No days selected"
            : alarm.weekdays.map((d) => DAY_LABELS[d]).join(" ");

    return html`
      <div class="card ${alarm.enabled ? "" : "dim"}">
        <div class="row">
          <div class="time">${alarm.time}</div>
          <div class="grow">
            <div class="name">${alarm.name}</div>
            <div class="sub">${days}</div>
            <div class="sub">${alarm.media_player || "no player"}</div>
          </div>
          <div class="right">
            ${this._haForm
              ? html`<ha-switch
                  .checked=${alarm.enabled}
                  @change=${() => this._toggle(alarm)}
                ></ha-switch>`
              : html`<input
                  type="checkbox"
                  .checked=${alarm.enabled}
                  @change=${() => this._toggle(alarm)}
                />`}
            <div class="next">${this._fmtNext(alarm)}</div>
          </div>
        </div>
        ${alarm.is_ringing || alarm.is_snoozed || alarm.skip_next
          ? html`<div class="flags">
              ${alarm.is_ringing ? html`<span class="flag ring">Ringing</span>` : nothing}
              ${alarm.is_snoozed ? html`<span class="flag">Snoozed</span>` : nothing}
              ${alarm.skip_next ? html`<span class="flag">Skipping next</span>` : nothing}
            </div>`
          : nothing}
        ${html`<div class="actions">
              <button @click=${() => this._openEdit(alarm)}>Edit</button>
              <button @click=${() => this._skip(alarm)}>
                ${alarm.skip_next ? "Don't skip" : "Skip next"}
              </button>
              <button @click=${() => this._trigger(alarm)}>Test</button>
              <button class="danger" @click=${() => this._delete(alarm)}>Delete</button>
            </div>`}
      </div>
    `;
  }

  private _renderRinging() {
    const ringing = this._alarms.filter((a) => a.is_ringing || a.is_snoozed);
    if (!ringing.length) return nothing;
    return html`
      <div class="banner">
        <div class="grow">
          <strong>${ringing.map((a) => a.name).join(", ")}</strong>
          <div class="sub">${ringing[0].is_snoozed ? "Snoozed" : "Ringing now"}</div>
        </div>
        <button @click=${() => this._call({ type: "wakey/snooze" })}>Snooze</button>
        <button @click=${() => this._call({ type: "wakey/dismiss" })}>Dismiss</button>
      </div>
    `;
  }

  private _renderDialog() {
    if (!this._dialogOpen) return nothing;
    return html`
      <div class="scrim" @click=${this._closeDialog}></div>
      <div class="dialog" role="dialog" aria-modal="true">
        <h2>${this._editing ? "Edit alarm" : "New alarm"}</h2>
        ${this._haForm
          ? html`<ha-form
              .hass=${this.hass}
              .data=${this._draft}
              .schema=${this._schema()}
              .computeLabel=${this._label}
              @value-changed=${this._formChanged}
            ></ha-form>`
          : html`
              <p class="warn">
                Home Assistant's form components did not load, so this is a reduced editor.
              </p>
              <label>Name<input .value=${this._draft.name ?? ""} @input=${(e: any) =>
                (this._draft = { ...this._draft, name: e.target.value })} /></label>
              <label>Time<input type="time" .value=${this._draft.time ?? "07:00"} @input=${(e: any) =>
                (this._draft = { ...this._draft, time: e.target.value })} /></label>
              <label>Media player<input .value=${this._draft.media_player ?? ""} @input=${(e: any) =>
                (this._draft = { ...this._draft, media_player: e.target.value })} /></label>
              <label>Source<input .value=${this._draft.source_uri ?? ""} @input=${(e: any) =>
                (this._draft = { ...this._draft, source_uri: e.target.value })} /></label>
            `}
        <div class="dialog-actions">
          <button @click=${this._closeDialog}>Cancel</button>
          <button class="primary" @click=${this._save}>Save</button>
        </div>
      </div>
    `;
  }

  private _renderEmpty() {
    if (!this._canCreate) {
      return html`<div class="empty">
        An administrator has not given you access to any speakers yet, so there is
        nowhere for an alarm to play.
      </div>`;
    }
    return html`<div class="empty">No alarms yet. Use Add alarm to create one.</div>`;
  }

  private _renderAlarms() {
    if (!this._loaded) return html`<div class="empty">Loading…</div>`;
    if (this._alarms.length === 0) return this._renderEmpty();
    return this._alarms.map((a) => this._renderAlarm(a));
  }

  protected render() {
    const admin = this._view === "admin";
    return html`
      <div class="header">
        <h1>Wakey</h1>
        ${this._isAdmin
          ? html`<div class="tabs">
              <button
                class=${admin ? "" : "selected"}
                @click=${() => (this._view = "alarms")}
              >
                Alarms
              </button>
              <button
                class=${admin ? "selected" : ""}
                @click=${() => (this._view = "admin")}
              >
                People
              </button>
            </div>`
          : nothing}
        ${!admin && this._canCreate
          ? html`<button class="primary" @click=${this._openNew}>Add alarm</button>`
          : nothing}
      </div>

      <div class="body">
        ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
        ${admin
          ? html`<wakey-admin
              .hass=${this.hass}
              .alarms=${this._alarms}
              .haForm=${this._haForm}
            ></wakey-admin>`
          : html`${this._renderRinging()} ${this._renderAlarms()}`}
      </div>

      ${this._renderDialog()}
    `;
  }

  static styles = css`
    :host {
      display: block;
      min-height: 100vh;
      background: var(--primary-background-color, #f5f5f5);
      color: var(--primary-text-color, #212121);
      font-family: var(--paper-font-body1_-_font-family, inherit);
    }
    .header {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 16px 20px;
      background: var(--app-header-background-color, var(--primary-color, #03a9f4));
      color: var(--app-header-text-color, #fff);
    }
    .header h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 400;
      flex: 1;
    }
    .body {
      padding: 16px;
      max-width: 720px;
      margin: 0 auto;
      padding-bottom: calc(24px + var(--safe-area-inset-bottom, 0px));
    }
    .card {
      background: var(--card-background-color, #fff);
      border-radius: var(--ha-card-border-radius, 12px);
      box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0, 0, 0, 0.1));
      padding: 16px;
      margin-bottom: 12px;
    }
    .card.dim {
      opacity: 0.55;
    }
    .row {
      display: flex;
      align-items: center;
      gap: 16px;
    }
    .grow {
      flex: 1;
      min-width: 0;
    }
    .time {
      font-size: clamp(2rem, 9vw, 2.75rem);
      font-variant-numeric: tabular-nums;
      line-height: 1;
      font-weight: 300;
    }
    .name {
      font-weight: 500;
    }
    .sub {
      color: var(--secondary-text-color, #727272);
      font-size: 13px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .right {
      text-align: right;
    }
    .next {
      font-size: 12px;
      color: var(--secondary-text-color, #727272);
      margin-top: 4px;
    }
    .flags {
      margin-top: 10px;
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .flag {
      font-size: 12px;
      padding: 2px 8px;
      border-radius: 10px;
      background: var(--secondary-background-color, #e0e0e0);
    }
    .flag.ring {
      background: var(--error-color, #db4437);
      color: #fff;
    }
    .actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 12px;
      border-top: 1px solid var(--divider-color, #e0e0e0);
      padding-top: 12px;
    }
    button {
      font: inherit;
      font-size: 14px;
      padding: 8px 14px;
      border-radius: 8px;
      border: 1px solid var(--divider-color, #e0e0e0);
      background: transparent;
      color: var(--primary-color, #03a9f4);
      cursor: pointer;
    }
    button.primary {
      background: var(--primary-color, #03a9f4);
      color: var(--text-primary-color, #fff);
      border-color: transparent;
    }
    button.danger {
      color: var(--error-color, #db4437);
    }
    .tabs {
      display: flex;
      gap: 4px;
    }
    .tabs button {
      color: inherit;
      border-color: transparent;
      opacity: 0.75;
    }
    .tabs button.selected {
      opacity: 1;
      border-bottom: 2px solid currentColor;
      border-radius: 8px 8px 0 0;
    }
    .banner {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 14px 16px;
      margin-bottom: 12px;
      border-radius: var(--ha-card-border-radius, 12px);
      background: var(--error-color, #db4437);
      color: #fff;
    }
    .banner button {
      color: #fff;
      border-color: rgba(255, 255, 255, 0.6);
    }
    .banner .sub {
      color: rgba(255, 255, 255, 0.85);
    }
    .empty,
    .error {
      padding: 32px 16px;
      text-align: center;
      color: var(--secondary-text-color, #727272);
    }
    .error {
      color: var(--error-color, #db4437);
    }
    .scrim {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.45);
      z-index: 10;
    }
    .dialog {
      position: fixed;
      z-index: 11;
      left: 50%;
      top: 50%;
      transform: translate(-50%, -50%);
      width: min(560px, calc(100vw - 32px));
      max-height: calc(100vh - 64px);
      overflow: auto;
      background: var(--card-background-color, #fff);
      color: var(--primary-text-color, #212121);
      border-radius: var(--ha-card-border-radius, 12px);
      padding: 20px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }
    .dialog h2 {
      margin: 0 0 16px;
      font-size: 18px;
      font-weight: 500;
    }
    .dialog label {
      display: block;
      margin-bottom: 12px;
      font-size: 13px;
      color: var(--secondary-text-color, #727272);
    }
    .dialog input {
      display: block;
      width: 100%;
      box-sizing: border-box;
      margin-top: 4px;
      padding: 8px;
      font: inherit;
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 6px;
      background: var(--card-background-color, #fff);
      color: var(--primary-text-color, #212121);
    }
    .dialog-actions {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      margin-top: 20px;
    }
    .warn {
      color: var(--warning-color, #ffa600);
      font-size: 13px;
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "wakey-panel": WakeyPanel;
  }
}
