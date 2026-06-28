/* @ds-bundle: {"format":3,"namespace":"LittleMovieStoreDesignSystem_a217bb","components":[{"name":"ProductCard","sourcePath":"components/commerce/ProductCard.jsx"},{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Card","sourcePath":"components/core/Card.jsx"},{"name":"Eyebrow","sourcePath":"components/core/Eyebrow.jsx"},{"name":"Input","sourcePath":"components/core/Input.jsx"}],"sourceHashes":{"components/commerce/ProductCard.jsx":"3b8ca6f9c453","components/core/Badge.jsx":"04ebe191d708","components/core/Button.jsx":"b4586c3dc318","components/core/Card.jsx":"165492c87bb2","components/core/Eyebrow.jsx":"5c3c457fd7fc","components/core/Input.jsx":"ae61cfbabc8c","ui_kits/website/chrome.jsx":"bdebf99d7ceb","ui_kits/website/screens.jsx":"2f4790705271"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.LittleMovieStoreDesignSystem_a217bb = window.LittleMovieStoreDesignSystem_a217bb || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/core/Badge.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Little Movie Store — Badge / Format tag
 * Small uppercase label for formats (4K, VHS, USED, NEW) and statuses.
 */
function Badge({
  children,
  tone = "neutral",
  variant = "soft",
  style,
  ...rest
}) {
  const tones = {
    neutral: {
      solid: "var(--lms-mahogany)",
      soft: "var(--lms-ink-100)",
      softText: "var(--lms-ink-700)"
    },
    brick: {
      solid: "var(--lms-brick)",
      soft: "var(--lms-brick-tint)",
      softText: "var(--lms-brick)"
    },
    sage: {
      solid: "var(--lms-sage)",
      soft: "var(--lms-sage-tint)",
      softText: "var(--lms-sage-dark)"
    },
    cyan: {
      solid: "var(--lms-cyan)",
      soft: "var(--lms-cyan-tint)",
      softText: "var(--lms-hunter)"
    },
    hunter: {
      solid: "var(--lms-hunter)",
      soft: "var(--lms-sage-tint)",
      softText: "var(--lms-hunter)"
    }
  };
  const t = tones[tone] || tones.neutral;
  const styles = variant === "solid" ? {
    background: t.solid,
    color: "var(--lms-parchment)",
    border: "var(--border-width) solid transparent"
  } : variant === "outline" ? {
    background: "transparent",
    color: t.softText,
    border: "var(--border-width) solid currentColor"
  } : {
    background: t.soft,
    color: t.softText,
    border: "var(--border-width) solid transparent"
  };
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "5px",
      fontFamily: "var(--font-mono)",
      fontWeight: "var(--fw-mono-med)",
      fontSize: "10px",
      letterSpacing: "0.14em",
      textTransform: "uppercase",
      padding: "4px 9px",
      borderRadius: "var(--radius-xs)",
      lineHeight: 1,
      whiteSpace: "nowrap",
      ...styles,
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/commerce/ProductCard.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Little Movie Store — ProductCard
 * A shelf item: cover, title, format/condition tags, price. The cover falls
 * back to a parchment "poster" placeholder when no image is supplied.
 */
function ProductCard({
  title,
  director,
  price,
  image,
  format,
  // e.g. "4K", "Blu-ray", "VHS", "DVD"
  condition,
  // "New" | "Used"
  rare = false,
  accent = "var(--lms-mahogany)",
  onClick,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("div", _extends({
    onClick: onClick,
    style: {
      display: "flex",
      flexDirection: "column",
      cursor: onClick ? "pointer" : "default",
      transition: "transform var(--dur-base) var(--ease-soft)",
      ...style
    },
    onMouseEnter: e => {
      e.currentTarget.style.transform = "translateY(-4px)";
    },
    onMouseLeave: e => {
      e.currentTarget.style.transform = "translateY(0)";
    }
  }, rest), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      aspectRatio: "3 / 4",
      borderRadius: "var(--radius-md)",
      overflow: "hidden",
      background: image ? `center/cover no-repeat url(${image})` : accent,
      border: "var(--border-width) solid var(--border-default)",
      boxShadow: "var(--shadow-sm)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center"
    }
  }, !image && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-display)",
      fontWeight: 600,
      fontSize: "20px",
      color: "var(--lms-parchment)",
      textAlign: "center",
      padding: "0 18px",
      lineHeight: 1.15,
      opacity: 0.92
    }
  }, title), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      top: "8px",
      left: "8px",
      display: "flex",
      gap: "5px"
    }
  }, format && /*#__PURE__*/React.createElement(__ds_scope.Badge, {
    tone: "cyan",
    variant: "solid"
  }, format), rare && /*#__PURE__*/React.createElement(__ds_scope.Badge, {
    tone: "brick",
    variant: "solid"
  }, "Rare"))), /*#__PURE__*/React.createElement("div", {
    style: {
      paddingTop: "12px",
      display: "flex",
      flexDirection: "column",
      gap: "3px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "baseline",
      justifyContent: "space-between",
      gap: "10px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-display)",
      fontWeight: 500,
      fontSize: "16px",
      color: "var(--text-strong)",
      lineHeight: 1.2
    }
  }, title), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      fontWeight: 500,
      fontSize: "15px",
      color: "var(--color-primary)",
      whiteSpace: "nowrap"
    }
  }, price)), director && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      fontWeight: 300,
      fontSize: "12px",
      color: "var(--text-muted)"
    }
  }, director), condition && /*#__PURE__*/React.createElement("span", {
    style: {
      marginTop: "4px"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Badge, {
    tone: condition === "New" ? "sage" : "neutral"
  }, condition))));
}
Object.assign(__ds_scope, { ProductCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/commerce/ProductCard.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Little Movie Store — Button
 * Warm, friendly, lived-in. Brick primary, sage/parchment alternates.
 */
function Button({
  children,
  variant = "primary",
  size = "md",
  as = "button",
  iconLeft,
  iconRight,
  disabled = false,
  style,
  ...rest
}) {
  const sizes = {
    sm: {
      padding: "8px 16px",
      fontSize: "12px"
    },
    md: {
      padding: "12px 22px",
      fontSize: "13px"
    },
    lg: {
      padding: "16px 30px",
      fontSize: "15px"
    }
  };
  const variants = {
    primary: {
      background: "var(--color-primary)",
      color: "var(--text-on-brick)",
      border: "var(--border-width) solid var(--color-primary)"
    },
    secondary: {
      background: "var(--lms-mahogany)",
      color: "var(--text-on-dark)",
      border: "var(--border-width) solid var(--lms-mahogany)"
    },
    outline: {
      background: "transparent",
      color: "var(--text-strong)",
      border: "var(--border-width) solid var(--border-strong)"
    },
    sage: {
      background: "var(--lms-sage)",
      color: "var(--lms-parchment)",
      border: "var(--border-width) solid var(--lms-sage)"
    },
    ghost: {
      background: "transparent",
      color: "var(--text-strong)",
      border: "var(--border-width) solid transparent"
    }
  };
  const Tag = as;
  return /*#__PURE__*/React.createElement(Tag, _extends({
    disabled: Tag === "button" ? disabled : undefined,
    style: {
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      gap: "8px",
      fontFamily: "var(--font-mono)",
      fontWeight: "var(--fw-mono-med)",
      letterSpacing: "0.04em",
      textTransform: "uppercase",
      borderRadius: "0",
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.5 : 1,
      textDecoration: "none",
      lineHeight: 1,
      transition: "transform var(--dur-fast) var(--ease-soft), filter var(--dur-fast) var(--ease-soft)",
      ...sizes[size],
      ...variants[variant],
      ...style
    },
    onMouseDown: e => {
      if (!disabled) e.currentTarget.style.transform = "scale(0.97)";
    },
    onMouseUp: e => {
      e.currentTarget.style.transform = "scale(1)";
    },
    onMouseLeave: e => {
      e.currentTarget.style.transform = "scale(1)";
      e.currentTarget.style.filter = "none";
    },
    onMouseEnter: e => {
      if (!disabled) e.currentTarget.style.filter = "brightness(1.06)";
    }
  }, rest), iconLeft, children, iconRight);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Little Movie Store — Card
 * A lived-in surface: warm white, soft border, gentle radius, low warm shadow.
 */
function Card({
  children,
  elevated = false,
  padding = "24px",
  as = "div",
  style,
  ...rest
}) {
  const Tag = as;
  return /*#__PURE__*/React.createElement(Tag, _extends({
    style: {
      background: "var(--surface-card)",
      border: "var(--border-width) solid var(--border-default)",
      borderRadius: "var(--radius-lg)",
      boxShadow: elevated ? "var(--shadow-md)" : "var(--shadow-xs)",
      padding,
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Card.jsx", error: String((e && e.message) || e) }); }

// components/core/Eyebrow.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Little Movie Store — Eyebrow
 * The signature wide-tracked uppercase DM Mono label that sits above headings.
 */
function Eyebrow({
  children,
  tone = "brick",
  style,
  ...rest
}) {
  const colors = {
    brick: "var(--color-primary)",
    sage: "var(--lms-sage)",
    mahogany: "var(--lms-mahogany)",
    muted: "var(--text-muted)",
    parchment: "var(--lms-parchment)"
  };
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: "inline-block",
      fontFamily: "var(--font-mono)",
      fontWeight: "var(--fw-mono-med)",
      fontSize: "var(--fs-eyebrow)",
      letterSpacing: "var(--tracking-eyebrow)",
      textTransform: "uppercase",
      color: colors[tone] || colors.brick,
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Eyebrow });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Eyebrow.jsx", error: String((e && e.message) || e) }); }

// components/core/Input.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Little Movie Store — Input
 * Paper-feeling text field with a soft warm border and sage focus ring.
 */
function Input({
  label,
  hint,
  prefix,
  type = "text",
  style,
  id,
  ...rest
}) {
  const inputId = id || (label ? "in-" + label.replace(/\s+/g, "-").toLowerCase() : undefined);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "6px",
      width: "100%"
    }
  }, label && /*#__PURE__*/React.createElement("label", {
    htmlFor: inputId,
    style: {
      fontFamily: "var(--font-mono)",
      fontWeight: "var(--fw-mono-med)",
      fontSize: "11px",
      letterSpacing: "0.1em",
      textTransform: "uppercase",
      color: "var(--text-muted)"
    }
  }, label), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      background: "var(--surface-card)",
      border: "var(--border-width) solid var(--border-default)",
      borderRadius: "var(--radius-sm)",
      padding: "0 14px",
      transition: "border-color var(--dur-fast) var(--ease-soft), box-shadow var(--dur-fast) var(--ease-soft)"
    },
    onFocusCapture: e => {
      e.currentTarget.style.borderColor = "var(--lms-sage)";
      e.currentTarget.style.boxShadow = "0 0 0 3px var(--lms-sage-tint)";
    },
    onBlurCapture: e => {
      e.currentTarget.style.borderColor = "var(--border-default)";
      e.currentTarget.style.boxShadow = "none";
    }
  }, prefix && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      color: "var(--text-muted)",
      marginRight: "8px",
      fontSize: "14px"
    }
  }, prefix), /*#__PURE__*/React.createElement("input", _extends({
    id: inputId,
    type: type,
    style: {
      flex: 1,
      border: "none",
      outline: "none",
      background: "transparent",
      fontFamily: "var(--font-mono)",
      fontWeight: "var(--fw-mono-light)",
      fontSize: "15px",
      color: "var(--text-strong)",
      padding: "12px 0",
      ...style
    }
  }, rest))), hint && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "12px",
      color: "var(--text-muted)"
    }
  }, hint));
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Input.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/chrome.jsx
try { (() => {
/* Little Movie Store — Website chrome: Header, Ticker, Newsletter, Footer */
const NS = window.LittleMovieStoreDesignSystem_a217bb;
const {
  Button,
  Badge,
  Eyebrow,
  Input
} = NS;
const ASSET = "../../assets";
const NAV = ["Shop", "Rental Library", "Events", "About"];
const GENRES = ["All genres", "Horror", "Sci-Fi", "Kids", "Action", "Comedy", "Romance"];
function Header({
  view,
  setView,
  genre,
  setGenre,
  cartCount
}) {
  return /*#__PURE__*/React.createElement("header", {
    style: {
      position: "sticky",
      top: 0,
      zIndex: 20,
      background: "color-mix(in oklch, var(--lms-parchment) 88%, transparent)",
      backdropFilter: "blur(10px)",
      borderBottom: "1.5px solid var(--border-default)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "var(--container-max)",
      margin: "0 auto",
      padding: "0 28px",
      height: "72px",
      display: "flex",
      alignItems: "center",
      gap: "28px"
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: `${ASSET}/logos/logo-horizontal.svg`,
    alt: "Little Movie Store",
    onClick: () => setView("home"),
    style: {
      height: "26px",
      cursor: "pointer"
    }
  }), /*#__PURE__*/React.createElement("nav", {
    style: {
      display: "flex",
      gap: "22px",
      marginLeft: "8px"
    }
  }, NAV.map(n => {
    const target = n === "Shop" ? "shop" : n.toLowerCase().replace(/\s+/g, "");
    const active = view === target;
    return /*#__PURE__*/React.createElement("button", {
      key: n,
      onClick: () => setView(n === "Shop" ? "shop" : "home"),
      style: {
        border: "none",
        background: "none",
        cursor: "pointer",
        fontFamily: "var(--font-mono)",
        fontWeight: active ? 500 : 300,
        fontSize: "13px",
        letterSpacing: "0.04em",
        color: active ? "var(--color-primary)" : "var(--text-body)",
        padding: 0
      }
    }, n);
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("label", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "8px",
      cursor: "pointer"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "lms-eyebrow",
    style: {
      fontSize: "10px"
    }
  }, "Genre Mode"), /*#__PURE__*/React.createElement("select", {
    value: genre,
    onChange: e => setGenre(e.target.value),
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "12px",
      fontWeight: 500,
      color: "var(--text-strong)",
      background: "var(--surface-card)",
      border: "1.5px solid var(--border-default)",
      borderRadius: "var(--radius-pill)",
      padding: "7px 14px",
      cursor: "pointer",
      letterSpacing: "0.03em"
    }
  }, GENRES.map(g => /*#__PURE__*/React.createElement("option", {
    key: g
  }, g)))), /*#__PURE__*/React.createElement(Button, {
    size: "sm",
    variant: "primary",
    onClick: () => setView("join")
  }, "Join the club"), /*#__PURE__*/React.createElement("button", {
    "aria-label": "Bag",
    style: {
      position: "relative",
      border: "1.5px solid var(--border-strong)",
      background: "none",
      borderRadius: "var(--radius-pill)",
      width: "38px",
      height: "38px",
      cursor: "pointer",
      fontFamily: "var(--font-mono)",
      fontSize: "15px",
      color: "var(--text-strong)"
    }
  }, "\u2315")));
}
const TICKER_ITEMS = ["4K Restorations", "VHS", "Steelbooks", "Mystery Bags", "Boutique Labels", "Blu-ray", "Movie Books", "Enamel Pins", "Weekly Drops", "Rare Finds", "Snacks", "Media Players"];
function Ticker({
  accent = "var(--lms-mahogany)"
}) {
  const row = [...TICKER_ITEMS, ...TICKER_ITEMS];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: accent,
      overflow: "hidden",
      padding: "11px 0",
      borderBottom: "1.5px solid rgba(0,0,0,0.12)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "inline-flex",
      gap: "0",
      whiteSpace: "nowrap",
      animation: "lms-marquee 38s linear infinite"
    }
  }, row.map((t, i) => /*#__PURE__*/React.createElement("span", {
    key: i,
    style: {
      fontFamily: "var(--font-mono)",
      fontWeight: 500,
      fontSize: "12px",
      letterSpacing: "0.14em",
      textTransform: "uppercase",
      color: "var(--lms-parchment)",
      padding: "0 20px",
      display: "inline-flex",
      alignItems: "center",
      gap: "20px"
    }
  }, t, /*#__PURE__*/React.createElement("span", {
    style: {
      opacity: 0.5
    }
  }, "\u2726")))));
}
function Newsletter() {
  return /*#__PURE__*/React.createElement("section", {
    style: {
      background: "var(--lms-hunter)",
      padding: "72px 28px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "620px",
      margin: "0 auto",
      textAlign: "center"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, {
    tone: "parchment"
  }, "Be our friend"), /*#__PURE__*/React.createElement("h2", {
    style: {
      color: "var(--lms-parchment)",
      fontSize: "34px",
      fontWeight: 500,
      margin: "16px 0 12px"
    }
  }, "Get the weekly drop in your inbox"), /*#__PURE__*/React.createElement("p", {
    style: {
      color: "color-mix(in oklch, var(--lms-parchment) 80%, transparent)",
      fontFamily: "var(--font-mono)",
      fontWeight: 300,
      fontSize: "15px",
      margin: "0 0 28px"
    }
  }, "New arrivals, members events, and the occasional movie night kit. No spam, just good taste."), /*#__PURE__*/React.createElement("form", {
    onSubmit: e => e.preventDefault(),
    style: {
      display: "flex",
      gap: "10px",
      maxWidth: "440px",
      margin: "0 auto"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement(Input, {
    placeholder: "you@email.com",
    type: "email"
  })), /*#__PURE__*/React.createElement(Button, {
    variant: "primary"
  }, "Sign up"))));
}
function Footer({
  setView
}) {
  const cols = {
    "Shop": ["New arrivals", "4K & Blu-ray", "Used & VHS", "Mystery bags", "Gift cards"],
    "Visit": ["Passyunk Ave, Philly", "Hours & map", "Rental library", "Events calendar"],
    "The Club": ["Join the club", "Member perks", "Borrow buddy", "Refer a friend"]
  };
  return /*#__PURE__*/React.createElement("footer", {
    style: {
      background: "var(--lms-mahogany)",
      color: "var(--lms-parchment)",
      padding: "64px 28px 36px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "var(--container-max)",
      margin: "0 auto",
      display: "grid",
      gridTemplateColumns: "1.4fr 1fr 1fr 1fr",
      gap: "40px"
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("img", {
    src: `${ASSET}/logos/logo-stacked-tagline-current.svg`,
    alt: "Little Movie Store",
    style: {
      height: "120px",
      color: "var(--lms-parchment)"
    }
  })), Object.entries(cols).map(([h, links]) => /*#__PURE__*/React.createElement("div", {
    key: h
  }, /*#__PURE__*/React.createElement("div", {
    className: "lms-eyebrow",
    style: {
      color: "var(--lms-cyan)",
      marginBottom: "16px"
    }
  }, h), /*#__PURE__*/React.createElement("ul", {
    style: {
      listStyle: "none",
      margin: 0,
      padding: 0,
      display: "flex",
      flexDirection: "column",
      gap: "10px"
    }
  }, links.map(l => /*#__PURE__*/React.createElement("li", {
    key: l
  }, /*#__PURE__*/React.createElement("a", {
    onClick: () => setView && setView("home"),
    style: {
      color: "color-mix(in oklch, var(--lms-parchment) 78%, transparent)",
      textDecoration: "none",
      fontFamily: "var(--font-mono)",
      fontWeight: 300,
      fontSize: "13px",
      cursor: "pointer"
    }
  }, l))))))), /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "var(--container-max)",
      margin: "44px auto 0",
      paddingTop: "24px",
      borderTop: "1.5px solid rgba(255,249,239,0.16)",
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      flexWrap: "wrap",
      gap: "12px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "12px",
      color: "rgba(255,249,239,0.6)"
    }
  }, "\xA9 2026 Little Movie Store \xB7 Made with love in South Philly"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "14px"
    }
  }, ["TikTok", "Instagram", "Threads"].map(s => /*#__PURE__*/React.createElement("a", {
    key: s,
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "12px",
      color: "var(--lms-cyan)",
      textDecoration: "none",
      cursor: "pointer",
      letterSpacing: "0.06em"
    }
  }, s)))));
}
Object.assign(window, {
  LMSHeader: Header,
  LMSTicker: Ticker,
  LMSNewsletter: Newsletter,
  LMSFooter: Footer,
  LMS_ASSET: ASSET
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/chrome.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/screens.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Little Movie Store — Website screens: Home, Shop, Product, Join the Club */
const NS_S = window.LittleMovieStoreDesignSystem_a217bb;
const {
  Button,
  Badge,
  Eyebrow,
  Card,
  ProductCard
} = NS_S;
const ASSET_S = window.LMS_ASSET;

/* ---- Sample shelf data (placeholders — no real covers on hand) ---- */
const ACCENTS = ["var(--lms-brick)", "var(--lms-hunter)", "var(--lms-sage)", "var(--lms-mahogany)", "var(--lms-brick-dark)"];
const FILMS = [{
  title: "Paris, Texas",
  director: "Wim Wenders",
  price: "$32",
  format: "4K",
  condition: "New",
  rare: true
}, {
  title: "The Goonies",
  director: "Richard Donner",
  price: "$8",
  format: "VHS",
  condition: "Used"
}, {
  title: "Spirited Away",
  director: "Hayao Miyazaki",
  price: "$18",
  format: "DVD",
  condition: "Used"
}, {
  title: "In the Mood for Love",
  director: "Wong Kar-wai",
  price: "$28",
  format: "Blu-ray",
  condition: "New"
}, {
  title: "The Thing",
  director: "John Carpenter",
  price: "$22",
  format: "4K",
  condition: "New",
  rare: true
}, {
  title: "Clueless",
  director: "Amy Heckerling",
  price: "$10",
  format: "DVD",
  condition: "Used"
}, {
  title: "Akira",
  director: "Katsuhiro Otomo",
  price: "$26",
  format: "Blu-ray",
  condition: "New"
}, {
  title: "Labyrinth",
  director: "Jim Henson",
  price: "$9",
  format: "VHS",
  condition: "Used"
}];
const withAccent = arr => arr.map((f, i) => ({
  ...f,
  accent: ACCENTS[i % ACCENTS.length]
}));
const GENRE_ACCENT = {
  "All genres": "var(--lms-mahogany)",
  "Horror": "#6e1414",
  "Sci-Fi": "var(--lms-hunter)",
  "Kids": "var(--lms-cyan)",
  "Action": "#a8430f",
  "Comedy": "#b8860b",
  "Romance": "#9c4f63"
};
function Section({
  children,
  bg,
  pad = "76px 28px"
}) {
  return /*#__PURE__*/React.createElement("section", {
    style: {
      background: bg || "transparent",
      padding: pad
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "var(--container-max)",
      margin: "0 auto"
    }
  }, children));
}
function SectionHead({
  eyebrow,
  title,
  action,
  onAction
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "flex-end",
      justifyContent: "space-between",
      marginBottom: "32px",
      gap: "20px",
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Eyebrow, null, eyebrow), /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: "30px",
      fontWeight: 500,
      marginTop: "10px"
    }
  }, title)), action && /*#__PURE__*/React.createElement(Button, {
    variant: "outline",
    size: "sm",
    onClick: onAction
  }, action));
}

/* ===================== HOME ===================== */
function HomeScreen({
  setView,
  genre,
  openProduct
}) {
  const accent = GENRE_ACCENT[genre] || "var(--lms-mahogany)";
  const films = withAccent(FILMS);
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Section, {
    pad: "84px 28px 64px"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1.05fr 0.95fr",
      gap: "48px",
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Eyebrow, null, "Now open on Passyunk Ave"), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: "60px",
      fontWeight: 600,
      lineHeight: 1.02,
      margin: "18px 0 0",
      letterSpacing: "-0.01em"
    }
  }, "Meet me at the movie store."), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: "var(--font-mono)",
      fontWeight: 300,
      fontSize: "17px",
      lineHeight: 1.6,
      color: "var(--text-body)",
      maxWidth: "440px",
      margin: "22px 0 32px"
    }
  }, "A movie store, reimagined for today. Physical media, curated by people who genuinely love movies \u2014 slow down, browse, and find something you'll fall for."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "14px"
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    size: "lg",
    onClick: () => setView("shop")
  }, "Browse the shelves"), /*#__PURE__*/React.createElement(Button, {
    variant: "outline",
    size: "lg",
    onClick: () => setView("join")
  }, "Join the club"))), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      aspectRatio: "4/3",
      borderRadius: "var(--radius-xl)",
      background: `radial-gradient(circle at 30% 30%, color-mix(in oklch, ${accent} 86%, white), ${accent})`,
      overflow: "hidden",
      border: "2px solid var(--border-strong)",
      boxShadow: "var(--shadow-lg)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center"
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: `${ASSET_S}/logos/logo-stacked-tagline-current.svg`,
    alt: "",
    style: {
      height: "62%",
      color: "var(--lms-parchment)",
      position: "relative",
      zIndex: 2
    }
  }), /*#__PURE__*/React.createElement("img", {
    src: `${ASSET_S}/monograms/tape-current.svg`,
    alt: "",
    style: {
      position: "absolute",
      width: "70px",
      color: "rgba(255,249,239,0.22)",
      top: "12%",
      left: "10%",
      animation: "lms-float 7s ease-in-out infinite"
    }
  }), /*#__PURE__*/React.createElement("img", {
    src: `${ASSET_S}/monograms/circles-current.svg`,
    alt: "",
    style: {
      position: "absolute",
      width: "56px",
      color: "rgba(255,249,239,0.20)",
      bottom: "14%",
      right: "12%",
      animation: "lms-float 9s ease-in-out infinite reverse"
    }
  }), /*#__PURE__*/React.createElement("img", {
    src: `${ASSET_S}/monograms/looped-current.svg`,
    alt: "",
    style: {
      position: "absolute",
      width: "50px",
      color: "rgba(255,249,239,0.18)",
      bottom: "20%",
      left: "16%",
      animation: "lms-float 8s ease-in-out infinite"
    }
  })))), /*#__PURE__*/React.createElement(window.LMSTicker, {
    accent: accent
  }), /*#__PURE__*/React.createElement(Section, null, /*#__PURE__*/React.createElement(SectionHead, {
    eyebrow: "Fresh on the shelf",
    title: "New arrivals this week",
    action: "Shop all",
    onAction: () => setView("shop")
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(4, 1fr)",
      gap: "26px"
    }
  }, films.slice(0, 4).map(f => /*#__PURE__*/React.createElement(ProductCard, _extends({
    key: f.title
  }, f, {
    onClick: () => openProduct(f)
  }))))), /*#__PURE__*/React.createElement(Section, {
    bg: "var(--lms-parchment-2)"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1fr 1fr",
      gap: "48px",
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      aspectRatio: "4/3",
      borderRadius: "var(--radius-lg)",
      background: "var(--lms-brick)",
      border: "2px solid var(--border-strong)",
      boxShadow: "var(--shadow-md)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "40px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-display)",
      fontWeight: 600,
      fontSize: "40px",
      color: "var(--lms-parchment)",
      textAlign: "center",
      lineHeight: 1.05
    }
  }, "The Criterion Wall")), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Eyebrow, null, "Featured this week"), /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: "36px",
      fontWeight: 500,
      margin: "12px 0 14px"
    }
  }, "Boutique labels, hand-picked"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: "var(--font-mono)",
      fontWeight: 300,
      fontSize: "16px",
      lineHeight: 1.6,
      color: "var(--text-body)",
      maxWidth: "440px",
      marginBottom: "10px"
    }
  }, "Steelbooks, restorations, and limited editions worth holding onto. We rotate the feature every week \u2014 this one's a love letter to slow cinema."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "8px",
      margin: "0 0 26px"
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "brick",
    variant: "solid"
  }, "Limited"), /*#__PURE__*/React.createElement(Badge, {
    tone: "cyan",
    variant: "solid"
  }, "4K"), /*#__PURE__*/React.createElement(Badge, {
    tone: "sage"
  }, "Collector")), /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    onClick: () => setView("shop")
  }, "Shop the feature")))), /*#__PURE__*/React.createElement(Section, null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1fr 1fr",
      gap: "26px"
    }
  }, /*#__PURE__*/React.createElement(Card, {
    padding: "40px",
    style: {
      background: "var(--lms-sage)",
      border: "none"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, {
    tone: "parchment"
  }, "This month"), /*#__PURE__*/React.createElement("h3", {
    style: {
      color: "var(--lms-parchment)",
      fontSize: "28px",
      fontWeight: 500,
      margin: "12px 0 10px"
    }
  }, "Members' movie nights"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: "var(--font-mono)",
      fontWeight: 300,
      fontSize: "15px",
      color: "color-mix(in oklch, var(--lms-parchment) 90%, transparent)",
      marginBottom: "24px"
    }
  }, "Cartoon mornings, horror closet tours, and screenings that spill into the park. Open invitations, never insider moments."), /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    size: "sm",
    onClick: () => setView("home")
  }, "See the calendar")), /*#__PURE__*/React.createElement(Card, {
    padding: "40px",
    style: {
      background: "var(--lms-mahogany)",
      border: "none"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, {
    tone: "parchment"
  }, "Little Movie Club"), /*#__PURE__*/React.createElement("h3", {
    style: {
      color: "var(--lms-parchment)",
      fontSize: "28px",
      fontWeight: 500,
      margin: "12px 0 10px"
    }
  }, "$100/year, all of the perks"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: "var(--font-mono)",
      fontWeight: 300,
      fontSize: "15px",
      color: "color-mix(in oklch, var(--lms-parchment) 88%, transparent)",
      marginBottom: "24px"
    }
  }, "Rental library access, 10% off everything, a free birthday movie, and invites to members events."), /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    size: "sm",
    onClick: () => setView("join")
  }, "Join the club")))), /*#__PURE__*/React.createElement(Section, {
    bg: "var(--lms-parchment-2)"
  }, /*#__PURE__*/React.createElement(SectionHead, {
    eyebrow: "From the staff",
    title: "Community picks"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(4, 1fr)",
      gap: "26px"
    }
  }, films.slice(4, 8).map(f => /*#__PURE__*/React.createElement(ProductCard, _extends({
    key: f.title
  }, f, {
    onClick: () => openProduct(f)
  })))), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: "var(--font-mono)",
      fontWeight: 300,
      fontSize: "13px",
      color: "var(--text-muted)",
      marginTop: "22px",
      textAlign: "center"
    }
  }, "\u2726 Every pick comes with a hand-written shelf note from whoever loved it most.")), /*#__PURE__*/React.createElement(window.LMSNewsletter, null), /*#__PURE__*/React.createElement(window.LMSFooter, {
    setView: setView
  }));
}

/* ===================== SHOP ===================== */
function ShopScreen({
  setView,
  openProduct
}) {
  const cats = ["All", "4K", "Blu-ray", "DVD", "VHS", "Boutique", "Used"];
  const [active, setActive] = React.useState("All");
  const films = withAccent([...FILMS, ...FILMS].map((f, i) => ({
    ...f,
    title: f.title
  })));
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Section, {
    pad: "56px 28px 28px"
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "The shelves"), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: "44px",
      fontWeight: 600,
      margin: "12px 0 6px"
    }
  }, "Shop everything"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: "var(--font-mono)",
      fontWeight: 300,
      fontSize: "15px",
      color: "var(--text-muted)"
    }
  }, "Used drives volume, boutique drives margin, and every shelf has a note. Browse without pressure."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "10px",
      flexWrap: "wrap",
      marginTop: "28px"
    }
  }, cats.map(c => /*#__PURE__*/React.createElement("button", {
    key: c,
    onClick: () => setActive(c),
    style: {
      fontFamily: "var(--font-mono)",
      fontWeight: 500,
      fontSize: "12px",
      letterSpacing: "0.06em",
      textTransform: "uppercase",
      padding: "9px 16px",
      borderRadius: "var(--radius-pill)",
      cursor: "pointer",
      border: "1.5px solid " + (active === c ? "var(--color-primary)" : "var(--border-default)"),
      background: active === c ? "var(--color-primary)" : "transparent",
      color: active === c ? "var(--lms-parchment)" : "var(--text-body)"
    }
  }, c)))), /*#__PURE__*/React.createElement(Section, {
    pad: "20px 28px 80px"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(4, 1fr)",
      gap: "28px"
    }
  }, films.slice(0, 12).map((f, i) => /*#__PURE__*/React.createElement(ProductCard, _extends({
    key: i
  }, f, {
    onClick: () => openProduct(f)
  }))))), /*#__PURE__*/React.createElement(window.LMSFooter, {
    setView: setView
  }));
}

/* ===================== PRODUCT ===================== */
function ProductScreen({
  film,
  setView
}) {
  const f = film || withAccent(FILMS)[0];
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Section, {
    pad: "48px 28px 80px"
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => setView("shop"),
    style: {
      border: "none",
      background: "none",
      cursor: "pointer",
      fontFamily: "var(--font-mono)",
      fontSize: "13px",
      color: "var(--text-muted)",
      marginBottom: "28px",
      padding: 0
    }
  }, "\u2190 Back to the shelves"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "0.8fr 1fr",
      gap: "56px",
      alignItems: "start"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      aspectRatio: "3/4",
      borderRadius: "var(--radius-lg)",
      background: f.accent || "var(--lms-brick)",
      border: "2px solid var(--border-strong)",
      boxShadow: "var(--shadow-lg)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "32px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-display)",
      fontWeight: 600,
      fontSize: "30px",
      color: "var(--lms-parchment)",
      textAlign: "center",
      lineHeight: 1.1
    }
  }, f.title)), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "8px",
      marginBottom: "16px"
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "cyan",
    variant: "solid"
  }, f.format), /*#__PURE__*/React.createElement(Badge, {
    tone: f.condition === "New" ? "sage" : "neutral"
  }, f.condition), f.rare && /*#__PURE__*/React.createElement(Badge, {
    tone: "brick",
    variant: "solid"
  }, "Rare find")), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: "42px",
      fontWeight: 600,
      lineHeight: 1.05,
      marginBottom: "8px"
    }
  }, f.title), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: "var(--font-mono)",
      fontWeight: 300,
      fontSize: "16px",
      color: "var(--text-muted)",
      marginBottom: "22px"
    }
  }, "Directed by ", f.director), /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: "var(--font-mono)",
      fontWeight: 500,
      fontSize: "28px",
      color: "var(--color-primary)",
      marginBottom: "28px"
    }
  }, f.price), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "12px",
      marginBottom: "32px"
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    size: "lg"
  }, "Add to bag"), /*#__PURE__*/React.createElement(Button, {
    variant: "outline",
    size: "lg"
  }, "Rent it \xB7 $4")), /*#__PURE__*/React.createElement(Card, {
    padding: "22px",
    style: {
      background: "var(--lms-parchment-2)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "lms-eyebrow",
    style: {
      marginBottom: "10px"
    }
  }, "Shelf note \xB7 from Ace"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: "var(--font-mono)",
      fontWeight: 300,
      fontSize: "14px",
      lineHeight: 1.6,
      color: "var(--text-body)",
      margin: 0
    }
  }, "\"One of those movies that rewards a big screen and a slow night. If you liked the feeling of wandering, this one's for you. Pairs well with the pizza spot two doors down.\""))))), /*#__PURE__*/React.createElement(window.LMSFooter, {
    setView: setView
  }));
}

/* ===================== JOIN THE CLUB ===================== */
function JoinScreen({
  setView
}) {
  const perks = [["Rental library", "Access to the whole borrow-buddy library, all year."], ["10% off everything", "Every purchase, every visit, no fine print."], ["Free birthday movie", "Pick anything off the shelf — it's on us."], ["Members events", "First invites to screenings, tours, and movie nights."]];
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Section, {
    pad: "80px 28px",
    bg: "var(--lms-brick)"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: "center",
      maxWidth: "640px",
      margin: "0 auto"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, {
    tone: "parchment"
  }, "Little Movie Club \xB7 $100 / year"), /*#__PURE__*/React.createElement("h1", {
    style: {
      color: "var(--lms-parchment)",
      fontSize: "56px",
      fontWeight: 600,
      lineHeight: 1.02,
      margin: "18px 0 16px"
    }
  }, "Built by movie lovers, for everyone."), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: "var(--font-mono)",
      fontWeight: 300,
      fontSize: "17px",
      lineHeight: 1.6,
      color: "color-mix(in oklch, var(--lms-parchment) 88%, transparent)",
      marginBottom: "32px"
    }
  }, "The club isn't about the perks \u2014 it's about belonging to a place that's as much yours as it is ours. Renters become buyers. That's the whole game, baby."), /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    size: "lg"
  }, "Become a member"))), /*#__PURE__*/React.createElement(Section, null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(4, 1fr)",
      gap: "20px"
    }
  }, perks.map(([t, d], i) => /*#__PURE__*/React.createElement(Card, {
    key: t,
    padding: "28px",
    elevated: true
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: "var(--font-display)",
      fontWeight: 600,
      fontSize: "34px",
      color: "var(--lms-ink-200)",
      marginBottom: "14px"
    }
  }, String(i + 1).padStart(2, "0")), /*#__PURE__*/React.createElement("h3", {
    style: {
      fontSize: "19px",
      fontWeight: 500,
      marginBottom: "8px"
    }
  }, t), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: "var(--font-mono)",
      fontWeight: 300,
      fontSize: "13px",
      lineHeight: 1.55,
      color: "var(--text-muted)",
      margin: 0
    }
  }, d))))), /*#__PURE__*/React.createElement(window.LMSNewsletter, null), /*#__PURE__*/React.createElement(window.LMSFooter, {
    setView: setView
  }));
}
Object.assign(window, {
  LMSHome: HomeScreen,
  LMSShop: ShopScreen,
  LMSProduct: ProductScreen,
  LMSJoin: JoinScreen
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/screens.jsx", error: String((e && e.message) || e) }); }

__ds_ns.ProductCard = __ds_scope.ProductCard;

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.Eyebrow = __ds_scope.Eyebrow;

__ds_ns.Input = __ds_scope.Input;

})();
