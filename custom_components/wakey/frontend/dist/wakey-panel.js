/**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const M = globalThis, I = M.ShadowRoot && (M.ShadyCSS === void 0 || M.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype, q = Symbol(), K = /* @__PURE__ */ new WeakMap();
let oe = class {
  constructor(e, s, i) {
    if (this._$cssResult$ = !0, i !== q) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = e, this.t = s;
  }
  get styleSheet() {
    let e = this.o;
    const s = this.t;
    if (I && e === void 0) {
      const i = s !== void 0 && s.length === 1;
      i && (e = K.get(s)), e === void 0 && ((this.o = e = new CSSStyleSheet()).replaceSync(this.cssText), i && K.set(s, e));
    }
    return e;
  }
  toString() {
    return this.cssText;
  }
};
const _e = (t) => new oe(typeof t == "string" ? t : t + "", void 0, q), ne = (t, ...e) => {
  const s = t.length === 1 ? t[0] : e.reduce((i, r, a) => i + ((o) => {
    if (o._$cssResult$ === !0) return o.cssText;
    if (typeof o == "number") return o;
    throw Error("Value passed to 'css' function must be a 'css' function result: " + o + ". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.");
  })(r) + t[a + 1], t[0]);
  return new oe(s, t, q);
}, me = (t, e) => {
  if (I) t.adoptedStyleSheets = e.map((s) => s instanceof CSSStyleSheet ? s : s.styleSheet);
  else for (const s of e) {
    const i = document.createElement("style"), r = M.litNonce;
    r !== void 0 && i.setAttribute("nonce", r), i.textContent = s.cssText, t.appendChild(i);
  }
}, Y = I ? (t) => t : (t) => t instanceof CSSStyleSheet ? ((e) => {
  let s = "";
  for (const i of e.cssRules) s += i.cssText;
  return _e(s);
})(t) : t;
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const { is: fe, defineProperty: ge, getOwnPropertyDescriptor: ye, getOwnPropertyNames: $e, getOwnPropertySymbols: ve, getPrototypeOf: be } = Object, L = globalThis, G = L.trustedTypes, we = G ? G.emptyScript : "", xe = L.reactiveElementPolyfillSupport, j = (t, e) => t, H = { toAttribute(t, e) {
  switch (e) {
    case Boolean:
      t = t ? we : null;
      break;
    case Object:
    case Array:
      t = t == null ? t : JSON.stringify(t);
  }
  return t;
}, fromAttribute(t, e) {
  let s = t;
  switch (e) {
    case Boolean:
      s = t !== null;
      break;
    case Number:
      s = t === null ? null : Number(t);
      break;
    case Object:
    case Array:
      try {
        s = JSON.parse(t);
      } catch {
        s = null;
      }
  }
  return s;
} }, F = (t, e) => !fe(t, e), Q = { attribute: !0, type: String, converter: H, reflect: !1, useDefault: !1, hasChanged: F };
Symbol.metadata ??= Symbol("metadata"), L.litPropertyMetadata ??= /* @__PURE__ */ new WeakMap();
let k = class extends HTMLElement {
  static addInitializer(e) {
    this._$Ei(), (this.l ??= []).push(e);
  }
  static get observedAttributes() {
    return this.finalize(), this._$Eh && [...this._$Eh.keys()];
  }
  static createProperty(e, s = Q) {
    if (s.state && (s.attribute = !1), this._$Ei(), this.prototype.hasOwnProperty(e) && ((s = Object.create(s)).wrapped = !0), this.elementProperties.set(e, s), !s.noAccessor) {
      const i = Symbol(), r = this.getPropertyDescriptor(e, i, s);
      r !== void 0 && ge(this.prototype, e, r);
    }
  }
  static getPropertyDescriptor(e, s, i) {
    const { get: r, set: a } = ye(this.prototype, e) ?? { get() {
      return this[s];
    }, set(o) {
      this[s] = o;
    } };
    return { get: r, set(o) {
      const c = r?.call(this);
      a?.call(this, o), this.requestUpdate(e, c, i);
    }, configurable: !0, enumerable: !0 };
  }
  static getPropertyOptions(e) {
    return this.elementProperties.get(e) ?? Q;
  }
  static _$Ei() {
    if (this.hasOwnProperty(j("elementProperties"))) return;
    const e = be(this);
    e.finalize(), e.l !== void 0 && (this.l = [...e.l]), this.elementProperties = new Map(e.elementProperties);
  }
  static finalize() {
    if (this.hasOwnProperty(j("finalized"))) return;
    if (this.finalized = !0, this._$Ei(), this.hasOwnProperty(j("properties"))) {
      const s = this.properties, i = [...$e(s), ...ve(s)];
      for (const r of i) this.createProperty(r, s[r]);
    }
    const e = this[Symbol.metadata];
    if (e !== null) {
      const s = litPropertyMetadata.get(e);
      if (s !== void 0) for (const [i, r] of s) this.elementProperties.set(i, r);
    }
    this._$Eh = /* @__PURE__ */ new Map();
    for (const [s, i] of this.elementProperties) {
      const r = this._$Eu(s, i);
      r !== void 0 && this._$Eh.set(r, s);
    }
    this.elementStyles = this.finalizeStyles(this.styles);
  }
  static finalizeStyles(e) {
    const s = [];
    if (Array.isArray(e)) {
      const i = new Set(e.flat(1 / 0).reverse());
      for (const r of i) s.unshift(Y(r));
    } else e !== void 0 && s.push(Y(e));
    return s;
  }
  static _$Eu(e, s) {
    const i = s.attribute;
    return i === !1 ? void 0 : typeof i == "string" ? i : typeof e == "string" ? e.toLowerCase() : void 0;
  }
  constructor() {
    super(), this._$Ep = void 0, this.isUpdatePending = !1, this.hasUpdated = !1, this._$Em = null, this._$Ev();
  }
  _$Ev() {
    this._$ES = new Promise((e) => this.enableUpdating = e), this._$AL = /* @__PURE__ */ new Map(), this._$E_(), this.requestUpdate(), this.constructor.l?.forEach((e) => e(this));
  }
  addController(e) {
    (this._$EO ??= /* @__PURE__ */ new Set()).add(e), this.renderRoot !== void 0 && this.isConnected && e.hostConnected?.();
  }
  removeController(e) {
    this._$EO?.delete(e);
  }
  _$E_() {
    const e = /* @__PURE__ */ new Map(), s = this.constructor.elementProperties;
    for (const i of s.keys()) this.hasOwnProperty(i) && (e.set(i, this[i]), delete this[i]);
    e.size > 0 && (this._$Ep = e);
  }
  createRenderRoot() {
    const e = this.shadowRoot ?? this.attachShadow(this.constructor.shadowRootOptions);
    return me(e, this.constructor.elementStyles), e;
  }
  connectedCallback() {
    this.renderRoot ??= this.createRenderRoot(), this.enableUpdating(!0), this._$EO?.forEach((e) => e.hostConnected?.());
  }
  enableUpdating(e) {
  }
  disconnectedCallback() {
    this._$EO?.forEach((e) => e.hostDisconnected?.());
  }
  attributeChangedCallback(e, s, i) {
    this._$AK(e, i);
  }
  _$ET(e, s) {
    const i = this.constructor.elementProperties.get(e), r = this.constructor._$Eu(e, i);
    if (r !== void 0 && i.reflect === !0) {
      const a = (i.converter?.toAttribute !== void 0 ? i.converter : H).toAttribute(s, i.type);
      this._$Em = e, a == null ? this.removeAttribute(r) : this.setAttribute(r, a), this._$Em = null;
    }
  }
  _$AK(e, s) {
    const i = this.constructor, r = i._$Eh.get(e);
    if (r !== void 0 && this._$Em !== r) {
      const a = i.getPropertyOptions(r), o = typeof a.converter == "function" ? { fromAttribute: a.converter } : a.converter?.fromAttribute !== void 0 ? a.converter : H;
      this._$Em = r;
      const c = o.fromAttribute(s, a.type);
      this[r] = c ?? this._$Ej?.get(r) ?? c, this._$Em = null;
    }
  }
  requestUpdate(e, s, i, r = !1, a) {
    if (e !== void 0) {
      const o = this.constructor;
      if (r === !1 && (a = this[e]), i ??= o.getPropertyOptions(e), !((i.hasChanged ?? F)(a, s) || i.useDefault && i.reflect && a === this._$Ej?.get(e) && !this.hasAttribute(o._$Eu(e, i)))) return;
      this.C(e, s, i);
    }
    this.isUpdatePending === !1 && (this._$ES = this._$EP());
  }
  C(e, s, { useDefault: i, reflect: r, wrapped: a }, o) {
    i && !(this._$Ej ??= /* @__PURE__ */ new Map()).has(e) && (this._$Ej.set(e, o ?? s ?? this[e]), a !== !0 || o !== void 0) || (this._$AL.has(e) || (this.hasUpdated || i || (s = void 0), this._$AL.set(e, s)), r === !0 && this._$Em !== e && (this._$Eq ??= /* @__PURE__ */ new Set()).add(e));
  }
  async _$EP() {
    this.isUpdatePending = !0;
    try {
      await this._$ES;
    } catch (s) {
      Promise.reject(s);
    }
    const e = this.scheduleUpdate();
    return e != null && await e, !this.isUpdatePending;
  }
  scheduleUpdate() {
    return this.performUpdate();
  }
  performUpdate() {
    if (!this.isUpdatePending) return;
    if (!this.hasUpdated) {
      if (this.renderRoot ??= this.createRenderRoot(), this._$Ep) {
        for (const [r, a] of this._$Ep) this[r] = a;
        this._$Ep = void 0;
      }
      const i = this.constructor.elementProperties;
      if (i.size > 0) for (const [r, a] of i) {
        const { wrapped: o } = a, c = this[r];
        o !== !0 || this._$AL.has(r) || c === void 0 || this.C(r, void 0, a, c);
      }
    }
    let e = !1;
    const s = this._$AL;
    try {
      e = this.shouldUpdate(s), e ? (this.willUpdate(s), this._$EO?.forEach((i) => i.hostUpdate?.()), this.update(s)) : this._$EM();
    } catch (i) {
      throw e = !1, this._$EM(), i;
    }
    e && this._$AE(s);
  }
  willUpdate(e) {
  }
  _$AE(e) {
    this._$EO?.forEach((s) => s.hostUpdated?.()), this.hasUpdated || (this.hasUpdated = !0, this.firstUpdated(e)), this.updated(e);
  }
  _$EM() {
    this._$AL = /* @__PURE__ */ new Map(), this.isUpdatePending = !1;
  }
  get updateComplete() {
    return this.getUpdateComplete();
  }
  getUpdateComplete() {
    return this._$ES;
  }
  shouldUpdate(e) {
    return !0;
  }
  update(e) {
    this._$Eq &&= this._$Eq.forEach((s) => this._$ET(s, this[s])), this._$EM();
  }
  updated(e) {
  }
  firstUpdated(e) {
  }
};
k.elementStyles = [], k.shadowRootOptions = { mode: "open" }, k[j("elementProperties")] = /* @__PURE__ */ new Map(), k[j("finalized")] = /* @__PURE__ */ new Map(), xe?.({ ReactiveElement: k }), (L.reactiveElementVersions ??= []).push("2.1.2");
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const V = globalThis, X = (t) => t, R = V.trustedTypes, ee = R ? R.createPolicy("lit-html", { createHTML: (t) => t }) : void 0, le = "$lit$", b = `lit$${Math.random().toFixed(9).slice(2)}$`, de = "?" + b, Ae = `<${de}>`, A = document, T = () => A.createComment(""), N = (t) => t === null || typeof t != "object" && typeof t != "function", J = Array.isArray, ke = (t) => J(t) || typeof t?.[Symbol.iterator] == "function", B = `[ 	
\f\r]`, O = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g, te = /-->/g, se = />/g, w = RegExp(`>|${B}(?:([^\\s"'>=/]+)(${B}*=${B}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g"), ie = /'/g, re = /"/g, ce = /^(?:script|style|textarea|title)$/i, Se = (t) => (e, ...s) => ({ _$litType$: t, strings: e, values: s }), l = Se(1), E = Symbol.for("lit-noChange"), d = Symbol.for("lit-nothing"), ae = /* @__PURE__ */ new WeakMap(), x = A.createTreeWalker(A, 129);
function he(t, e) {
  if (!J(t) || !t.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return ee !== void 0 ? ee.createHTML(e) : e;
}
const Ee = (t, e) => {
  const s = t.length - 1, i = [];
  let r, a = e === 2 ? "<svg>" : e === 3 ? "<math>" : "", o = O;
  for (let c = 0; c < s; c++) {
    const n = t[c];
    let p, m, h = -1, y = 0;
    for (; y < n.length && (o.lastIndex = y, m = o.exec(n), m !== null); ) y = o.lastIndex, o === O ? m[1] === "!--" ? o = te : m[1] !== void 0 ? o = se : m[2] !== void 0 ? (ce.test(m[2]) && (r = RegExp("</" + m[2], "g")), o = w) : m[3] !== void 0 && (o = w) : o === w ? m[0] === ">" ? (o = r ?? O, h = -1) : m[1] === void 0 ? h = -2 : (h = o.lastIndex - m[2].length, p = m[1], o = m[3] === void 0 ? w : m[3] === '"' ? re : ie) : o === re || o === ie ? o = w : o === te || o === se ? o = O : (o = w, r = void 0);
    const v = o === w && t[c + 1].startsWith("/>") ? " " : "";
    a += o === O ? n + Ae : h >= 0 ? (i.push(p), n.slice(0, h) + le + n.slice(h) + b + v) : n + b + (h === -2 ? c : v);
  }
  return [he(t, a + (t[s] || "<?>") + (e === 2 ? "</svg>" : e === 3 ? "</math>" : "")), i];
};
class U {
  constructor({ strings: e, _$litType$: s }, i) {
    let r;
    this.parts = [];
    let a = 0, o = 0;
    const c = e.length - 1, n = this.parts, [p, m] = Ee(e, s);
    if (this.el = U.createElement(p, i), x.currentNode = this.el.content, s === 2 || s === 3) {
      const h = this.el.content.firstChild;
      h.replaceWith(...h.childNodes);
    }
    for (; (r = x.nextNode()) !== null && n.length < c; ) {
      if (r.nodeType === 1) {
        if (r.hasAttributes()) for (const h of r.getAttributeNames()) if (h.endsWith(le)) {
          const y = m[o++], v = r.getAttribute(h).split(b), D = /([.?@])?(.*)/.exec(y);
          n.push({ type: 1, index: a, name: D[2], strings: v, ctor: D[1] === "." ? Pe : D[1] === "?" ? Oe : D[1] === "@" ? je : W }), r.removeAttribute(h);
        } else h.startsWith(b) && (n.push({ type: 6, index: a }), r.removeAttribute(h));
        if (ce.test(r.tagName)) {
          const h = r.textContent.split(b), y = h.length - 1;
          if (y > 0) {
            r.textContent = R ? R.emptyScript : "";
            for (let v = 0; v < y; v++) r.append(h[v], T()), x.nextNode(), n.push({ type: 2, index: ++a });
            r.append(h[y], T());
          }
        }
      } else if (r.nodeType === 8) if (r.data === de) n.push({ type: 2, index: a });
      else {
        let h = -1;
        for (; (h = r.data.indexOf(b, h + 1)) !== -1; ) n.push({ type: 7, index: a }), h += b.length - 1;
      }
      a++;
    }
  }
  static createElement(e, s) {
    const i = A.createElement("template");
    return i.innerHTML = e, i;
  }
}
function C(t, e, s = t, i) {
  if (e === E) return e;
  let r = i !== void 0 ? s._$Co?.[i] : s._$Cl;
  const a = N(e) ? void 0 : e._$litDirective$;
  return r?.constructor !== a && (r?._$AO?.(!1), a === void 0 ? r = void 0 : (r = new a(t), r._$AT(t, s, i)), i !== void 0 ? (s._$Co ??= [])[i] = r : s._$Cl = r), r !== void 0 && (e = C(t, r._$AS(t, e.values), r, i)), e;
}
class Ce {
  constructor(e, s) {
    this._$AV = [], this._$AN = void 0, this._$AD = e, this._$AM = s;
  }
  get parentNode() {
    return this._$AM.parentNode;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  u(e) {
    const { el: { content: s }, parts: i } = this._$AD, r = (e?.creationScope ?? A).importNode(s, !0);
    x.currentNode = r;
    let a = x.nextNode(), o = 0, c = 0, n = i[0];
    for (; n !== void 0; ) {
      if (o === n.index) {
        let p;
        n.type === 2 ? p = new z(a, a.nextSibling, this, e) : n.type === 1 ? p = new n.ctor(a, n.name, n.strings, this, e) : n.type === 6 && (p = new Te(a, this, e)), this._$AV.push(p), n = i[++c];
      }
      o !== n?.index && (a = x.nextNode(), o++);
    }
    return x.currentNode = A, r;
  }
  p(e) {
    let s = 0;
    for (const i of this._$AV) i !== void 0 && (i.strings !== void 0 ? (i._$AI(e, i, s), s += i.strings.length - 2) : i._$AI(e[s])), s++;
  }
}
class z {
  get _$AU() {
    return this._$AM?._$AU ?? this._$Cv;
  }
  constructor(e, s, i, r) {
    this.type = 2, this._$AH = d, this._$AN = void 0, this._$AA = e, this._$AB = s, this._$AM = i, this.options = r, this._$Cv = r?.isConnected ?? !0;
  }
  get parentNode() {
    let e = this._$AA.parentNode;
    const s = this._$AM;
    return s !== void 0 && e?.nodeType === 11 && (e = s.parentNode), e;
  }
  get startNode() {
    return this._$AA;
  }
  get endNode() {
    return this._$AB;
  }
  _$AI(e, s = this) {
    e = C(this, e, s), N(e) ? e === d || e == null || e === "" ? (this._$AH !== d && this._$AR(), this._$AH = d) : e !== this._$AH && e !== E && this._(e) : e._$litType$ !== void 0 ? this.$(e) : e.nodeType !== void 0 ? this.T(e) : ke(e) ? this.k(e) : this._(e);
  }
  O(e) {
    return this._$AA.parentNode.insertBefore(e, this._$AB);
  }
  T(e) {
    this._$AH !== e && (this._$AR(), this._$AH = this.O(e));
  }
  _(e) {
    this._$AH !== d && N(this._$AH) ? this._$AA.nextSibling.data = e : this.T(A.createTextNode(e)), this._$AH = e;
  }
  $(e) {
    const { values: s, _$litType$: i } = e, r = typeof i == "number" ? this._$AC(e) : (i.el === void 0 && (i.el = U.createElement(he(i.h, i.h[0]), this.options)), i);
    if (this._$AH?._$AD === r) this._$AH.p(s);
    else {
      const a = new Ce(r, this), o = a.u(this.options);
      a.p(s), this.T(o), this._$AH = a;
    }
  }
  _$AC(e) {
    let s = ae.get(e.strings);
    return s === void 0 && ae.set(e.strings, s = new U(e)), s;
  }
  k(e) {
    J(this._$AH) || (this._$AH = [], this._$AR());
    const s = this._$AH;
    let i, r = 0;
    for (const a of e) r === s.length ? s.push(i = new z(this.O(T()), this.O(T()), this, this.options)) : i = s[r], i._$AI(a), r++;
    r < s.length && (this._$AR(i && i._$AB.nextSibling, r), s.length = r);
  }
  _$AR(e = this._$AA.nextSibling, s) {
    for (this._$AP?.(!1, !0, s); e !== this._$AB; ) {
      const i = X(e).nextSibling;
      X(e).remove(), e = i;
    }
  }
  setConnected(e) {
    this._$AM === void 0 && (this._$Cv = e, this._$AP?.(e));
  }
}
class W {
  get tagName() {
    return this.element.tagName;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  constructor(e, s, i, r, a) {
    this.type = 1, this._$AH = d, this._$AN = void 0, this.element = e, this.name = s, this._$AM = r, this.options = a, i.length > 2 || i[0] !== "" || i[1] !== "" ? (this._$AH = Array(i.length - 1).fill(new String()), this.strings = i) : this._$AH = d;
  }
  _$AI(e, s = this, i, r) {
    const a = this.strings;
    let o = !1;
    if (a === void 0) e = C(this, e, s, 0), o = !N(e) || e !== this._$AH && e !== E, o && (this._$AH = e);
    else {
      const c = e;
      let n, p;
      for (e = a[0], n = 0; n < a.length - 1; n++) p = C(this, c[i + n], s, n), p === E && (p = this._$AH[n]), o ||= !N(p) || p !== this._$AH[n], p === d ? e = d : e !== d && (e += (p ?? "") + a[n + 1]), this._$AH[n] = p;
    }
    o && !r && this.j(e);
  }
  j(e) {
    e === d ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, e ?? "");
  }
}
class Pe extends W {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(e) {
    this.element[this.name] = e === d ? void 0 : e;
  }
}
class Oe extends W {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(e) {
    this.element.toggleAttribute(this.name, !!e && e !== d);
  }
}
class je extends W {
  constructor(e, s, i, r, a) {
    super(e, s, i, r, a), this.type = 5;
  }
  _$AI(e, s = this) {
    if ((e = C(this, e, s, 0) ?? d) === E) return;
    const i = this._$AH, r = e === d && i !== d || e.capture !== i.capture || e.once !== i.once || e.passive !== i.passive, a = e !== d && (i === d || r);
    r && this.element.removeEventListener(this.name, this, i), a && this.element.addEventListener(this.name, this, e), this._$AH = e;
  }
  handleEvent(e) {
    typeof this._$AH == "function" ? this._$AH.call(this.options?.host ?? this.element, e) : this._$AH.handleEvent(e);
  }
}
class Te {
  constructor(e, s, i) {
    this.element = e, this.type = 6, this._$AN = void 0, this._$AM = s, this.options = i;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(e) {
    C(this, e);
  }
}
const Ne = V.litHtmlPolyfillSupport;
Ne?.(U, z), (V.litHtmlVersions ??= []).push("3.3.3");
const Ue = (t, e, s) => {
  const i = s?.renderBefore ?? e;
  let r = i._$litPart$;
  if (r === void 0) {
    const a = s?.renderBefore ?? null;
    i._$litPart$ = r = new z(e.insertBefore(T(), a), a, void 0, s ?? {});
  }
  return r._$AI(t), r;
};
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const Z = globalThis;
class S extends k {
  constructor() {
    super(...arguments), this.renderOptions = { host: this }, this._$Do = void 0;
  }
  createRenderRoot() {
    const e = super.createRenderRoot();
    return this.renderOptions.renderBefore ??= e.firstChild, e;
  }
  update(e) {
    const s = this.render();
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(e), this._$Do = Ue(s, this.renderRoot, this.renderOptions);
  }
  connectedCallback() {
    super.connectedCallback(), this._$Do?.setConnected(!0);
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this._$Do?.setConnected(!1);
  }
  render() {
    return E;
  }
}
S._$litElement$ = !0, S.finalized = !0, Z.litElementHydrateSupport?.({ LitElement: S });
const ze = Z.litElementPolyfillSupport;
ze?.({ LitElement: S });
(Z.litElementVersions ??= []).push("4.2.2");
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const pe = (t) => (e, s) => {
  s !== void 0 ? s.addInitializer(() => {
    customElements.define(t, e);
  }) : customElements.define(t, e);
};
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const De = { attribute: !0, type: String, converter: H, reflect: !1, hasChanged: F }, Me = (t = De, e, s) => {
  const { kind: i, metadata: r } = s;
  let a = globalThis.litPropertyMetadata.get(r);
  if (a === void 0 && globalThis.litPropertyMetadata.set(r, a = /* @__PURE__ */ new Map()), i === "setter" && ((t = Object.create(t)).wrapped = !0), a.set(s.name, t), i === "accessor") {
    const { name: o } = s;
    return { set(c) {
      const n = e.get.call(this);
      e.set.call(this, c), this.requestUpdate(o, n, t, !0, c);
    }, init(c) {
      return c !== void 0 && this.C(o, void 0, t, c), c;
    } };
  }
  if (i === "setter") {
    const { name: o } = s;
    return function(c) {
      const n = this[o];
      e.call(this, c), this.requestUpdate(o, n, t, !0, c);
    };
  }
  throw Error("Unsupported decorator location: " + i);
};
function P(t) {
  return (e, s) => typeof s == "object" ? Me(t, e, s) : ((i, r, a) => {
    const o = r.hasOwnProperty(a);
    return r.constructor.createProperty(a, i), o ? Object.getOwnPropertyDescriptor(r, a) : void 0;
  })(t, e, s);
}
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
function _(t) {
  return P({ ...t, state: !0, attribute: !1 });
}
const ue = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], He = () => ({
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
  enabled: !0,
  notify_targets: [],
  resume_previous: !1
});
async function Re() {
  try {
    await (await (await window.loadCardHelpers?.())?.createCardElement({ type: "entities", entities: [] }))?.constructor?.getConfigElement?.();
  } catch {
  }
  return Promise.race([
    customElements.whenDefined("ha-form").then(() => !0),
    new Promise((t) => setTimeout(() => t(!1), 4e3))
  ]);
}
var Le = Object.defineProperty, We = Object.getOwnPropertyDescriptor, $ = (t, e, s, i) => {
  for (var r = i > 1 ? void 0 : i ? We(e, s) : e, a = t.length - 1, o; a >= 0; a--)
    (o = t[a]) && (r = (i ? o(e, s, r) : o(r)) || r);
  return i && r && Le(e, s, r), r;
};
let g = class extends S {
  constructor() {
    super(...arguments), this.alarms = [], this.haForm = !1, this._users = [], this._policies = {}, this._orphans = {}, this._error = null, this._loaded = !1, this._saveTimers = {};
  }
  connectedCallback() {
    super.connectedCallback(), this._load();
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    for (const t of Object.values(this._saveTimers)) clearTimeout(t);
    this._saveTimers = {};
  }
  async _load() {
    try {
      const [t, e] = await Promise.all([
        this.hass.callWS({ type: "wakey/users/list" }),
        this.hass.callWS({
          type: "wakey/policy/list"
        })
      ]);
      this._users = t.users, this._policies = e.policies, this._loaded = !0;
    } catch (t) {
      this._error = t?.message ?? String(t), this._loaded = !0;
    }
  }
  _allowed(t) {
    return this._policies[t]?.allowed_media_players ?? [];
  }
  // --- speaker permissions -------------------------------------------------
  _policyChanged(t, e) {
    const s = e.detail.value?.allowed_media_players ?? [];
    this._policies = {
      ...this._policies,
      [t.id]: { user_id: t.id, allowed_media_players: s }
    }, clearTimeout(this._saveTimers[t.id]), this._saveTimers[t.id] = window.setTimeout(() => this._savePolicy(t), 600);
  }
  async _savePolicy(t) {
    try {
      const e = await this.hass.callWS({
        type: "wakey/policy/set",
        user_id: t.id,
        allowed_media_players: this._allowed(t.id)
      });
      this._policies = { ...this._policies, [t.id]: e.policy }, this._orphans = { ...this._orphans, [t.id]: e.orphaned_alarms }, this._error = null;
    } catch (e) {
      this._error = e?.message ?? String(e);
    }
  }
  _policySchema() {
    return [
      {
        name: "allowed_media_players",
        selector: {
          entity: { multiple: !0, filter: { domain: "media_player" } }
        }
      }
    ];
  }
  _renderUser(t) {
    const e = this._allowed(t.id), s = this._orphans[t.id] ?? [];
    return l`
      <div class="card">
        <div class="row">
          <div class="grow">
            <div class="name">${t.name || "Unnamed user"}</div>
            <div class="sub">
              ${t.is_admin ? "Administrator — every speaker" : e.length === 0 ? "No speakers yet" : `${e.length} speaker${e.length === 1 ? "" : "s"}`}
            </div>
          </div>
        </div>
        ${t.is_admin ? d : l`
              <div class="form">
                ${this.haForm ? l`<ha-form
                      .hass=${this.hass}
                      .data=${{ allowed_media_players: e }}
                      .schema=${this._policySchema()}
                      .computeLabel=${() => "Allowed speakers"}
                      @value-changed=${(i) => this._policyChanged(t, i)}
                    ></ha-form>` : l`<label>
                      Allowed speakers (comma separated)
                      <input
                        .value=${e.join(", ")}
                        @change=${(i) => this._policyChanged(t, {
      detail: {
        value: {
          allowed_media_players: i.target.value.split(",").map((r) => r.trim()).filter(Boolean)
        }
      }
    })}
                      />
                    </label>`}
              </div>
              ${s.length ? l`<div class="warn">
                    ${s.length} of ${t.name}'s alarms use a speaker they can
                    no longer choose:
                    ${s.map((i) => `${i.name} (${i.media_player})`).join(", ")}.
                    They will still go off — reassign or delete them.
                  </div>` : d}
            `}
      </div>
    `;
  }
  // --- ownership -----------------------------------------------------------
  async _setOwner(t, e) {
    try {
      await this.hass.callWS({
        type: "wakey/set_owner",
        alarm_id: t,
        owner_id: e
      }), this._error = null;
    } catch (s) {
      this._error = s?.message ?? String(s);
    }
  }
  get _unowned() {
    return this.alarms.filter((t) => !t.owner_id);
  }
  async _claimAll() {
    const t = this.hass.user?.id;
    if (t)
      for (const e of this._unowned)
        await this._setOwner(e.id, t);
  }
  _renderOwnership() {
    return this.alarms.length ? l`
      <h2>Who owns what</h2>
      ${this._unowned.length ? l`<div class="notice">
            <div class="grow">
              ${this._unowned.length}
              ${this._unowned.length === 1 ? "alarm has" : "alarms have"} no owner, so
              only administrators can see ${this._unowned.length === 1 ? "it" : "them"}.
            </div>
            <button class="primary" @click=${this._claimAll}>Assign all to me</button>
          </div>` : d}
      ${this.alarms.map(
      (t) => l`
          <div class="card">
            <div class="row">
              <div class="grow">
                <div class="name">${t.time} · ${t.name}</div>
                <div class="sub">${t.media_player || "no player"}</div>
              </div>
              <select
                .value=${t.owner_id ?? ""}
                @change=${(e) => this._setOwner(t.id, e.target.value || null)}
              >
                <option value="">Unassigned</option>
                ${this._users.map(
        (e) => l`<option value=${e.id} ?selected=${e.id === t.owner_id}>
                    ${e.name || e.id}
                  </option>`
      )}
              </select>
            </div>
          </div>
        `
    )}
    ` : d;
  }
  render() {
    return this._loaded ? l`
      ${this._error ? l`<div class="error">${this._error}</div>` : d}
      <h2>Speakers each person may use</h2>
      <p class="sub intro">
        Nobody gets a speaker until you grant it. Administrators always have all of
        them.
      </p>
      ${this._users.map((t) => this._renderUser(t))}
      ${this._renderOwnership()}
    ` : l`<div class="empty">Loading…</div>`;
  }
};
g.styles = ne`
    :host {
      display: block;
    }
    h2 {
      font-size: 16px;
      font-weight: 500;
      margin: 24px 0 4px;
    }
    .intro {
      margin: 0 0 12px;
    }
    .card {
      background: var(--card-background-color, #fff);
      border-radius: var(--ha-card-border-radius, 12px);
      box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0, 0, 0, 0.1));
      padding: 16px;
      margin-bottom: 12px;
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
    .name {
      font-weight: 500;
    }
    .sub {
      color: var(--secondary-text-color, #727272);
      font-size: 13px;
    }
    .form {
      margin-top: 8px;
    }
    .warn {
      margin-top: 10px;
      font-size: 13px;
      color: var(--warning-color, #ffa600);
    }
    .notice {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 14px 16px;
      margin-bottom: 12px;
      border-radius: var(--ha-card-border-radius, 12px);
      background: var(--secondary-background-color, #e0e0e0);
    }
    select,
    input {
      font: inherit;
      padding: 8px;
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 6px;
      background: var(--card-background-color, #fff);
      color: var(--primary-text-color, #212121);
    }
    input {
      display: block;
      width: 100%;
      box-sizing: border-box;
      margin-top: 4px;
    }
    label {
      display: block;
      font-size: 13px;
      color: var(--secondary-text-color, #727272);
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
      white-space: nowrap;
    }
    button.primary {
      background: var(--primary-color, #03a9f4);
      color: var(--text-primary-color, #fff);
      border-color: transparent;
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
  `;
$([
  P({ attribute: !1 })
], g.prototype, "hass", 2);
$([
  P({ attribute: !1 })
], g.prototype, "alarms", 2);
$([
  P({ attribute: !1 })
], g.prototype, "haForm", 2);
$([
  _()
], g.prototype, "_users", 2);
$([
  _()
], g.prototype, "_policies", 2);
$([
  _()
], g.prototype, "_orphans", 2);
$([
  _()
], g.prototype, "_error", 2);
$([
  _()
], g.prototype, "_loaded", 2);
g = $([
  pe("wakey-admin")
], g);
var Be = Object.defineProperty, Ie = Object.getOwnPropertyDescriptor, f = (t, e, s, i) => {
  for (var r = i > 1 ? void 0 : i ? Ie(e, s) : e, a = t.length - 1, o; a >= 0; a--)
    (o = t[a]) && (r = (i ? o(e, s, r) : o(r)) || r);
  return i && r && Be(e, s, r), r;
};
const qe = ue.map((t, e) => ({ value: String(e), label: t }));
let u = class extends S {
  constructor() {
    super(...arguments), this.narrow = !1, this._alarms = [], this._isAdmin = !1, this._allowedPlayers = null, this._view = "alarms", this._loaded = !1, this._error = null, this._dialogOpen = !1, this._editing = null, this._draft = {}, this._adjusting = null, this._adjustTime = "", this._haForm = !1, this._subscribed = !1, this._label = (t) => ({
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
      advanced: "Advanced"
    })[t.name] ?? t.name;
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this._unsub?.(), this._unsub = void 0, this._subscribed = !1;
  }
  updated(t) {
    t.has("hass") && this.hass && !this._subscribed && (this._subscribed = !0, this._subscribe(), Re().then((e) => this._haForm = e));
  }
  async _subscribe() {
    try {
      this._unsub = await this.hass.connection.subscribeMessage(
        (t) => {
          this._alarms = t.alarms ?? [], this._isAdmin = t.is_admin === !0, this._allowedPlayers = t.allowed_media_players ?? null, this._loaded = !0, this._error = null;
        },
        { type: "wakey/subscribe" }
      );
    } catch (t) {
      this._error = t?.message ?? String(t), this._loaded = !0;
    }
  }
  /**
   * Whether this user has anywhere to point a new alarm.
   *
   * Speakers are deny-by-default, so a household member who has not been
   * granted any cannot usefully create anything yet — and an Add button that
   * always fails is worse than no Add button.
   */
  get _canCreate() {
    return this._allowedPlayers === null || this._allowedPlayers.length > 0;
  }
  // --- actions -----------------------------------------------------------
  async _call(t) {
    try {
      return await this.hass.callWS(t), !0;
    } catch (e) {
      return this._error = e?.message ?? String(e), !1;
    }
  }
  _toggle(t) {
    this._call({ type: "wakey/update", alarm_id: t.id, enabled: !t.enabled });
  }
  _skip(t) {
    this._call({ type: "wakey/skip_next", alarm_id: t.id, skip: !t.skip_next });
  }
  /**
   * Whether a one-time adjustment is still ahead of us.
   *
   * The backend clears a spent adjustment on its next scheduling pass, which
   * can be a while after the day itself has gone. Checking the date here
   * keeps a dead one off the card in the meantime.
   */
  _adjusted(t) {
    return !t.override_for || !t.override_time ? !1 : t.override_for >= (/* @__PURE__ */ new Date()).toLocaleDateString("en-CA");
  }
  _openAdjust(t) {
    this._adjusting = t.id, this._adjustTime = t.override_time ?? t.time;
  }
  async _saveAdjust() {
    const t = this._adjusting;
    if (!t || !this._adjustTime) return;
    await this._call({
      type: "wakey/adjust_next",
      alarm_id: t,
      time: this._adjustTime.slice(0, 5)
    }) && (this._adjusting = null);
  }
  async _clearAdjust(t) {
    await this._call({ type: "wakey/adjust_next", alarm_id: t.id, clear: !0 }) && (this._adjusting = null);
  }
  _delete(t) {
    confirm(`Delete "${t.name}"?`) && this._call({ type: "wakey/delete", alarm_id: t.id });
  }
  _trigger(t) {
    this._call({ type: "wakey/trigger", alarm_id: t.id });
  }
  // --- dialog ------------------------------------------------------------
  _openNew() {
    this._editing = null, this._draft = { ...He(), weekdays: ["0", "1", "2", "3", "4"] }, this._dialogOpen = !0;
  }
  _openEdit(t) {
    this._editing = t.id, this._draft = {
      ...t,
      weekdays: (t.weekdays ?? []).map(String),
      media: t.media_player ? { entity_id: t.media_player } : void 0
    }, this._dialogOpen = !0;
  }
  _closeDialog() {
    this._dialogOpen = !1, this._editing = null;
  }
  _formChanged(t) {
    const e = { ...t.detail.value };
    e.media_player && e.media?.entity_id !== e.media_player && (e.media = { ...e.media ?? {}, entity_id: e.media_player }), e.media?.media_content_id && e.media.media_content_id !== this._draft.media?.media_content_id && (e.source_uri = e.media.media_content_id), this._draft = e;
  }
  async _save() {
    const t = this._draft;
    if (!t.time || !t.media_player || !t.source_uri) {
      this._error = "Name, time, media player and source are all required.";
      return;
    }
    const e = {
      name: t.name || "Alarm",
      time: String(t.time).slice(0, 5),
      repeat: t.repeat ?? "weekly",
      weekdays: (t.weekdays ?? []).map((s) => Number(s)),
      date: t.date ?? null,
      media_player: t.media_player,
      source_uri: t.source_uri,
      source_kind: t.source_kind ?? "music_assistant",
      volume: Number(t.volume ?? 0.7),
      fade_seconds: Number(t.fade_seconds ?? 0),
      resume_previous: !!(t.resume_previous ?? !1),
      snooze_minutes: Number(t.snooze_minutes ?? 9),
      auto_dismiss_minutes: Number(t.auto_dismiss_minutes ?? 30),
      pre_alarm_minutes: Number(t.pre_alarm_minutes ?? 0),
      pre_alarm_script: t.pre_alarm_script || null,
      notify_targets: t.notify_targets ?? []
    };
    this._editing ? await this._call({ type: "wakey/update", alarm_id: this._editing, ...e }) : await this._call({ type: "wakey/create", ...e, enabled: t.enabled ?? !0 }), this._closeDialog();
  }
  _schema() {
    const t = this._draft.repeat ?? "weekly";
    return [
      { name: "name", required: !0, selector: { text: {} } },
      { name: "time", required: !0, selector: { time: {} } },
      {
        name: "repeat",
        required: !0,
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "weekly", label: "Weekly" },
              { value: "once", label: "Once" }
            ]
          }
        }
      },
      ...t === "weekly" ? [{ name: "weekdays", selector: { select: { multiple: !0, options: qe } } }] : [{ name: "date", selector: { date: {} } }],
      {
        name: "media_player",
        required: !0,
        selector: {
          entity: {
            filter: { domain: "media_player" },
            // Omitted for admins, who are unrestricted. For everyone else
            // this is the whole point: the picker only offers the speakers
            // they were granted, so the refusal never has to happen.
            ...this._allowedPlayers ? { include_entities: this._allowedPlayers } : {}
          }
        }
      },
      { name: "media", selector: { media: {} } },
      { name: "source_uri", required: !0, selector: { text: {} } },
      {
        type: "grid",
        schema: [
          { name: "volume", selector: { number: { min: 0, max: 1, step: 0.05, mode: "slider" } } },
          {
            name: "fade_seconds",
            selector: { number: { min: 0, max: 900, step: 15, mode: "box", unit_of_measurement: "s" } }
          }
        ]
      },
      {
        type: "expandable",
        name: "advanced",
        title: "Advanced",
        schema: [
          {
            name: "snooze_minutes",
            selector: { number: { min: 1, max: 120, mode: "box", unit_of_measurement: "min" } }
          },
          {
            name: "auto_dismiss_minutes",
            selector: { number: { min: 1, max: 240, mode: "box", unit_of_measurement: "min" } }
          },
          {
            name: "pre_alarm_minutes",
            selector: { number: { min: 0, max: 240, mode: "box", unit_of_measurement: "min" } }
          },
          {
            name: "pre_alarm_script",
            selector: { entity: { filter: { domain: "script" } } }
          },
          {
            name: "notify_targets",
            selector: { entity: { multiple: !0, filter: { domain: "notify" } } }
          },
          { name: "resume_previous", selector: { boolean: {} } }
        ]
      }
    ];
  }
  // --- render ------------------------------------------------------------
  _fmtNext(t) {
    if (!t.enabled) return "Off";
    if (!t.next_fire) return "Never";
    const e = new Date(t.next_fire), s = Math.round((e.getTime() - Date.now()) / 6e4);
    if (s < 60) return `in ${Math.max(1, s)} min`;
    const i = Math.floor(s / 60);
    return i < 24 ? `in ${i}h ${s % 60}m` : e.toLocaleDateString(void 0, { weekday: "long" });
  }
  _fmtAdjusted(t) {
    const e = (/* @__PURE__ */ new Date()).toLocaleDateString("en-CA");
    return t.override_for === e ? `Today at ${t.override_time}` : `${(/* @__PURE__ */ new Date(`${t.override_for}T00:00:00`)).toLocaleDateString(void 0, { weekday: "long" })} at ${t.override_time}`;
  }
  _renderAdjustDialog() {
    const t = this._alarms.find((e) => e.id === this._adjusting);
    return t ? l`
      <div class="scrim" @click=${() => this._adjusting = null}></div>
      <div class="dialog" role="dialog" aria-modal="true">
        <h2>Adjust next</h2>
        <p class="hint">
          Just this once. ${t.name} rings at the new time, then goes back to
          ${t.time} on its own.
        </p>
        <label>
          Time
          <input
            type="time"
            .value=${this._adjustTime}
            @input=${(e) => this._adjustTime = e.target.value}
          />
        </label>
        <div class="dialog-actions">
          ${this._adjusted(t) ? l`<button @click=${() => this._clearAdjust(t)}>
                Back to ${t.time}
              </button>` : d}
          <button @click=${() => this._adjusting = null}>Cancel</button>
          <button class="primary" @click=${this._saveAdjust}>Save</button>
        </div>
      </div>
    ` : d;
  }
  _renderAlarm(t) {
    const e = t.repeat === "once" ? t.date ?? "Once" : t.weekdays.length === 7 ? "Every day" : t.weekdays.length === 0 ? "No days selected" : t.weekdays.map((s) => ue[s]).join(" ");
    return l`
      <div class="card ${t.enabled ? "" : "dim"}">
        <div class="row">
          <div class="time">${t.time}</div>
          <div class="grow">
            <div class="name">${t.name}</div>
            <div class="sub">${e}</div>
            <div class="sub">${t.media_player || "no player"}</div>
          </div>
          <div class="right">
            ${this._haForm ? l`<ha-switch
                  .checked=${t.enabled}
                  @change=${() => this._toggle(t)}
                ></ha-switch>` : l`<input
                  type="checkbox"
                  .checked=${t.enabled}
                  @change=${() => this._toggle(t)}
                />`}
            <div class="next">${this._fmtNext(t)}</div>
          </div>
        </div>
        ${t.is_ringing || t.is_snoozed || t.skip_next || this._adjusted(t) ? l`<div class="flags">
              ${t.is_ringing ? l`<span class="flag ring">Ringing</span>` : d}
              ${t.is_snoozed ? l`<span class="flag">Snoozed</span>` : d}
              ${t.skip_next ? l`<span class="flag">Skipping next</span>` : d}
              ${this._adjusted(t) ? l`<span class="flag">${this._fmtAdjusted(t)}</span>` : d}
            </div>` : d}
        ${l`<div class="actions">
              <button @click=${() => this._openEdit(t)}>Edit</button>
              <button @click=${() => this._skip(t)}>
                ${t.skip_next ? "Don't skip" : "Skip next"}
              </button>
              <button @click=${() => this._openAdjust(t)}>Adjust next</button>
              <button @click=${() => this._trigger(t)}>Test</button>
              <button class="danger" @click=${() => this._delete(t)}>Delete</button>
            </div>`}
      </div>
    `;
  }
  _renderRinging() {
    const t = this._alarms.filter((e) => e.is_ringing || e.is_snoozed);
    return t.length ? l`
      <div class="banner">
        <div class="grow">
          <strong>${t.map((e) => e.name).join(", ")}</strong>
          <div class="sub">${t[0].is_snoozed ? "Snoozed" : "Ringing now"}</div>
        </div>
        <button @click=${() => this._call({ type: "wakey/snooze" })}>Snooze</button>
        <button @click=${() => this._call({ type: "wakey/dismiss" })}>Dismiss</button>
      </div>
    ` : d;
  }
  _renderDialog() {
    return this._dialogOpen ? l`
      <div class="scrim" @click=${this._closeDialog}></div>
      <div class="dialog" role="dialog" aria-modal="true">
        <h2>${this._editing ? "Edit alarm" : "New alarm"}</h2>
        ${this._haForm ? l`<ha-form
              .hass=${this.hass}
              .data=${this._draft}
              .schema=${this._schema()}
              .computeLabel=${this._label}
              @value-changed=${this._formChanged}
            ></ha-form>` : l`
              <p class="warn">
                Home Assistant's form components did not load, so this is a reduced editor.
              </p>
              <label>Name<input .value=${this._draft.name ?? ""} @input=${(t) => this._draft = { ...this._draft, name: t.target.value }} /></label>
              <label>Time<input type="time" .value=${this._draft.time ?? "07:00"} @input=${(t) => this._draft = { ...this._draft, time: t.target.value }} /></label>
              <label>Media player<input .value=${this._draft.media_player ?? ""} @input=${(t) => this._draft = { ...this._draft, media_player: t.target.value }} /></label>
              <label>Source<input .value=${this._draft.source_uri ?? ""} @input=${(t) => this._draft = { ...this._draft, source_uri: t.target.value }} /></label>
            `}
        <div class="dialog-actions">
          <button @click=${this._closeDialog}>Cancel</button>
          <button class="primary" @click=${this._save}>Save</button>
        </div>
      </div>
    ` : d;
  }
  _renderEmpty() {
    return this._canCreate ? l`<div class="empty">No alarms yet. Use Add alarm to create one.</div>` : l`<div class="empty">
        An administrator has not given you access to any speakers yet, so there is
        nowhere for an alarm to play.
      </div>`;
  }
  _renderAlarms() {
    return this._loaded ? this._alarms.length === 0 ? this._renderEmpty() : this._alarms.map((t) => this._renderAlarm(t)) : l`<div class="empty">Loading…</div>`;
  }
  render() {
    const t = this._view === "admin";
    return l`
      <div class="header">
        <h1>Wakey</h1>
        ${this._isAdmin ? l`<div class="tabs">
              <button
                class=${t ? "" : "selected"}
                @click=${() => this._view = "alarms"}
              >
                Alarms
              </button>
              <button
                class=${t ? "selected" : ""}
                @click=${() => this._view = "admin"}
              >
                People
              </button>
            </div>` : d}
        ${!t && this._canCreate ? l`<button class="primary" @click=${this._openNew}>Add alarm</button>` : d}
      </div>

      <div class="body">
        ${this._error ? l`<div class="error">${this._error}</div>` : d}
        ${t ? l`<wakey-admin
              .hass=${this.hass}
              .alarms=${this._alarms}
              .haForm=${this._haForm}
            ></wakey-admin>` : l`${this._renderRinging()} ${this._renderAlarms()}`}
      </div>

      ${this._renderDialog()}
      ${this._adjusting ? this._renderAdjustDialog() : d}
    `;
  }
};
u.styles = ne`
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
    .dialog .hint {
      margin: -8px 0 16px;
      font-size: 13px;
      line-height: 1.4;
      color: var(--secondary-text-color, #727272);
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
f([
  P({ attribute: !1 })
], u.prototype, "hass", 2);
f([
  P({ attribute: !1 })
], u.prototype, "narrow", 2);
f([
  _()
], u.prototype, "_alarms", 2);
f([
  _()
], u.prototype, "_isAdmin", 2);
f([
  _()
], u.prototype, "_allowedPlayers", 2);
f([
  _()
], u.prototype, "_view", 2);
f([
  _()
], u.prototype, "_loaded", 2);
f([
  _()
], u.prototype, "_error", 2);
f([
  _()
], u.prototype, "_dialogOpen", 2);
f([
  _()
], u.prototype, "_editing", 2);
f([
  _()
], u.prototype, "_draft", 2);
f([
  _()
], u.prototype, "_adjusting", 2);
f([
  _()
], u.prototype, "_adjustTime", 2);
f([
  _()
], u.prototype, "_haForm", 2);
u = f([
  pe("wakey-panel")
], u);
