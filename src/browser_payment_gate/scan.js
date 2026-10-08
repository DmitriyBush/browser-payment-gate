// Page scan of browser-payment-gate. A function of the target element (or null when it
// was not found); runs INSIDE the page and returns a JSON string. All label matching
// happens in Python. Used two ways (scanner.py): a Playwright locator passes the element
// it resolved, so the scan and the click are the same element; other drivers evaluate
// scan_expression(selector), which looks the element up with document.querySelector.
function (el) {
  var FIELDS_MAX = 300, IFRAMES_MAX = 100;
  function txt(node){ try { return (node.textContent||'').slice(0,2000); } catch(e){ return ''; } }
  function fieldOf(e){
    return {autocomplete:(e.getAttribute('autocomplete')||''), name:(e.getAttribute('name')||''),
            id:(e.id||''), tag:e.tagName};
  }
  var out = {url: location.href, domain: location.hostname,
             title: (document.title||'').slice(0,200), heading:''};
  var h = document.querySelector('h1,h2,[role=heading]');
  out.heading = h ? (h.innerText||'').slice(0,200) : '';
  var fields = [], iframes = [], scanError = false;
  function collect(root){
    var els = root.querySelectorAll('input,select,textarea,iframe,[autocomplete]');
    for (var i=0;i<els.length;i++){
      var e = els[i];
      if (e.tagName === 'IFRAME'){ if (e.src) iframes.push(e.src); continue; }
      fields.push(fieldOf(e));
    }
    var all = root.querySelectorAll('*');
    for (var j=0;j<all.length;j++){
      if (all[j].shadowRoot){ collect(all[j].shadowRoot); }
    }
  }
  try { collect(document); } catch(e){ scanError = true; }
  out.fields = fields.slice(0, FIELDS_MAX);
  var srcs = [];
  for (var k=0;k<iframes.length && k<IFRAMES_MAX;k++){
    try { srcs.push(new URL(iframes[k], location.href).hostname); } catch(e){ srcs.push(String(iframes[k])); }
  }
  var bodyText = (document.body ? document.body.innerText : '') || '';
  // The whole amount ("$0.99" is not "$0"); grouped thousands ("1 990 ₽"); currency
  // before or after. Mirrors PRICE_RE in core.py.
  var amount = '\\d+(?:[ \\u00a0\\u202f]\\d{3})*(?:[.,]\\d+)*';
  var curBefore = '(?:\\$|\\u20ac|\\u00a3|\\u20bd|\\u20b8|\\b(?:USD|EUR|GBP|RUB|KZT|UAH|CHF)\\b)';
  var curAfter = '(?:\\$|\\u20ac|\\u00a3|\\u20bd|\\u20b8|(?:USD|EUR|GBP|RUB|KZT|UAH|CHF|\\u0440\\u0443\\u0431|\\u0442\\u0433)(?![a-z\\u0430-\\u044f\\u0451]))';
  var priceRe = new RegExp(curBefore + '\\s?' + amount + '|' + amount + '\\s?' + curAfter, 'i');
  out.signals = {
    orderTotal: /\b(total|order summary|amount due|subtotal)\b|итого|к оплате/i.test(bodyText),
    priceShown: priceRe.test(bodyText),
    priceAsImage: false,
    checkoutSummaryLayout: !!document.querySelector('[class*=checkout],[class*=order-summary],[id*=checkout],[class*=cart-summary]'),
    paymentIframe: false,
    iframeSrcs: srcs,
    blockedUrl: false,
    expressPay: /\b(apple ?pay|google ?pay|g ?pay)\b/i.test(bodyText),
    savedCardSelector: /\b(card )?ending in\b\s*\d|(\*{2,}|•{2,})\s?\d{4}\b/i.test(bodyText),
    fieldsTruncated: fields.length > FIELDS_MAX,
    iframesTruncated: iframes.length > IFRAMES_MAX,
    scanError: scanError
  };
  if (!el || el.nodeType !== 1){
    out.target = {found:false};
    return JSON.stringify(out);
  }
  // The control's block: the enclosing form if there is one, else the nearest wrapper
  // ABOVE the element (closest() would otherwise return a div-button itself).
  var up = el.parentElement || el;
  var anc = el.closest('form') || up.closest('section,[role=group],fieldset,div,li,tr,td') || up;
  // No wrapper below <body>: the whole page is not "next to" the control.
  if (anc === document.body || anc === document.documentElement){ anc = el; }
  var ancText = txt(anc);
  var m = ancText.match(priceRe);
  // Data fields of the form the control submits; buttons, fieldsets, outputs and objects carry no data.
  // formCut: more data fields than FIELDS_MAX -- the rest are not seen (core refuses such a submit).
  var formFields = [], formCut = false, NOT_DATA = {BUTTON:1, FIELDSET:1, OUTPUT:1, OBJECT:1};
  try {
    if (el.form){
      var nData = 0;
      for (var f=0; f<el.form.elements.length; f++){
        var fe = el.form.elements[f];
        if (NOT_DATA[fe.tagName] || /^(submit|button|reset|image)$/i.test(fe.type || '')) continue;
        nData++;
        if (nData <= FIELDS_MAX){ formFields.push(fieldOf(fe)); }
      }
      formCut = nData > FIELDS_MAX;
    }
  } catch(e){ out.signals.scanError = true; }
  var rawHref = el.getAttribute('href') || '';
  function noFrag(u){ return String(u||'').split('#')[0]; }
  // A script button dressed as a link is not navigation: href "#", "javascript:", or the
  // current page itself with no anchor. An in-page anchor ("#cite-12") is navigation.
  var scriptLink = !rawHref || rawHref === '#' || /^\s*javascript:/i.test(rawHref) ||
      (!!el.href && String(el.href).indexOf('#') < 0 && noFrag(el.href) === noFrag(location.href));
  out.target = {
    found:true, tag:el.tagName, type:(el.getAttribute('type')||''),
    text:(el.innerText||el.value||'').slice(0,120),
    aria:(el.getAttribute('aria-label')||''),
    autocomplete:(el.getAttribute('autocomplete')||''),
    name:(el.getAttribute('name')||''), id:(el.id||''),
    href:(!scriptLink && el.href) ? String(el.href) : '',
    isFormSubmit: (el.type === 'submit') || (el.type === 'image' && el.form != null) || (el.form != null && (el.tagName==='BUTTON' || el.type==='submit')),
    formFields: formFields,
    formFieldsTruncated: formCut,
    ancestorText: ancText,
    adjacentPrice: m ? m[0] : '',
    inClosedShadow:false
  };
  return JSON.stringify(out);
}
