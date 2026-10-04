// Page scan of browser-payment-gate. Runs INSIDE the page; returns a JSON string.
// The selector placeholder below is replaced by scanner.py with a JSON string literal. All label matching happens in Python.
(function(){
  function txt(el){ try { return (el.textContent||'').slice(0,2000); } catch(e){ return ''; } }
  var out = {url: location.href, domain: location.hostname,
             title: (document.title||'').slice(0,200), heading:'',
             ownArtifact: false};
  var h = document.querySelector('h1,h2,[role=heading]');
  out.heading = h ? (h.innerText||'').slice(0,200) : '';
  function collect(root, fields, iframes){
    var els = root.querySelectorAll('input,select,iframe,[autocomplete]');
    for (var i=0;i<els.length;i++){
      var e = els[i];
      if (e.tagName === 'IFRAME'){ if (e.src) iframes.push(e.src); continue; }
      fields.push({autocomplete:(e.getAttribute('autocomplete')||''),
                   name:(e.getAttribute('name')||''), id:(e.id||''), tag:e.tagName});
    }
    var all = root.querySelectorAll('*');
    for (var j=0;j<all.length;j++){
      var n = all[j];
      if (n.shadowRoot){ collect(n.shadowRoot, fields, iframes); }
    }
  }
  var fields = [], iframes = [];
  try { collect(document, fields, iframes); } catch(e){}
  out.fields = fields.slice(0,50);
  var srcs = [];
  for (var k=0;k<iframes.length && k<20;k++){ try { srcs.push(new URL(iframes[k]).hostname); } catch(e){ srcs.push(iframes[k]); } }
  var bodyText = (document.body ? document.body.innerText : '') || '';
  // the whole amount: "$0.99" must not be read as "$0" (free)
  var priceRe = /(\$|EUR|GBP|RUB|\u20ac|\u00a3|\u20bd)\s?\d+(?:[.,]\d+)*|\d+[.,]\d{2}\s?(\$|EUR|GBP|USD|RUB|\u20ac|\u00a3|\u20bd)/i;
  var sig = {
    orderTotal: /\b(total|order summary|amount due|subtotal)\b|\u0438\u0442\u043e\u0433\u043e|\u043a \u043e\u043f\u043b\u0430\u0442\u0435/i.test(bodyText),
    priceShown: priceRe.test(bodyText),
    priceAsImage: false,
    checkoutSummaryLayout: !!document.querySelector('[class*=checkout],[class*=order-summary],[id*=checkout],[class*=cart-summary]'),
    paymentIframe: false,
    iframeSrcs: srcs,
    blockedUrl: false,
    expressPay: /\b(apple ?pay|google ?pay|g ?pay)\b/i.test(bodyText),
    savedCardSelector: /\b(card )?ending in\b\s*\d|(\*{2,}|\u2022{2,})\s?\d{4}\b/i.test(bodyText),
    closedShadowOnPage: false,
    unresolvableControls: false
  };
  out.signals = sig;
  var sel = {SELECTOR};
  var el = null;
  try { el = document.querySelector(sel); } catch(e){ el = null; }
  if (!el){
    out.target = {found:false};
  } else {
    var anc = el.closest('form,section,[role=group],fieldset,div') || el.parentElement || el;
    out.target = {
      found:true, tag:el.tagName, type:(el.getAttribute('type')||''),
      text:(el.innerText||el.value||'').slice(0,120),
      aria:(el.getAttribute('aria-label')||''),
      autocomplete:(el.getAttribute('autocomplete')||''),
      name:(el.getAttribute('name')||''), id:(el.id||''),
      href:(el.href||''),
      isFormSubmit: (el.type === 'submit') || (el.form != null && (el.tagName==='BUTTON' || el.type==='submit')),
      ancestorText: txt(anc),
      adjacentPrice: (function(){ var m = txt(anc).match(priceRe); return m ? m[0] : ''; })(),
      inClosedShadow:false
    };
  }
  out.domHash = String((out.title+out.fields.length+srcs.length+(out.target.text||'')).length);
  return JSON.stringify(out);
})()
