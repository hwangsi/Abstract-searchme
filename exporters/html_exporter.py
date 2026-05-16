"""Generate a standalone viewer.html from a sessions.json file.

Usage:
    python -m exporters.html_exporter <sessions.json> [<output.html>]
"""
import json
import sys
from pathlib import Path

# Raw string: backslashes are literal → JS regex/string escapes pass through unchanged.
_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Conference Program</title>
<style>
*,*::before,*::after{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;background:#f0f2f5;color:#1a1a2e;min-height:100vh}
header{background:#fff;padding:18px 24px 14px;box-shadow:0 1px 4px rgba(0,0,0,.1);position:sticky;top:0;z-index:10}
h1{margin:0 0 3px;font-size:1.35em;color:#111}
#event-meta{color:#666;font-size:.88em;margin-bottom:12px}
#search{display:block;width:100%;max-width:520px;padding:9px 14px;font-size:1em;border:1.5px solid #ccc;border-radius:6px;outline:none;transition:border-color .15s,box-shadow .15s}
#search:focus{border-color:#4a90e2;box-shadow:0 0 0 3px rgba(74,144,226,.15)}
#result-count{margin-top:8px;font-size:.83em;color:#888;min-height:1.2em}
main{padding:16px 20px;max-width:1280px;margin:0 auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
.card{background:#fff;border-radius:8px;padding:14px 16px;box-shadow:0 1px 4px rgba(0,0,0,.07);border-left:4px solid #ddd;transition:box-shadow .15s}
.card:hover{box-shadow:0 3px 10px rgba(0,0,0,.13)}
.card-chair{border-left-color:#1d4ed8}
.card-speaker{border-left-color:#15803d}
.card-discussant{border-left-color:#c2410c}
.card-meta{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px}
.badge{font-size:.76em;padding:2px 8px;border-radius:12px;white-space:nowrap}
.b-date{background:#e8f0fe;color:#1a73e8}
.b-time{background:#e6f4ea;color:#188038}
.b-room{background:#fef7e0;color:#b45309}
.card-session{font-size:.84em;color:#555;margin-bottom:6px;line-height:1.4}
.card-person-line{margin-bottom:5px;font-size:.9em;display:flex;align-items:baseline;flex-wrap:wrap;gap:5px}
.role{padding:1px 7px;border-radius:4px;font-size:.75em;font-weight:700;letter-spacing:.05em;text-transform:uppercase;flex-shrink:0}
.role-chair{background:#dbeafe;color:#1d4ed8}
.role-speaker{background:#dcfce7;color:#15803d}
.role-discussant{background:#ffedd5;color:#c2410c}
.role-unknown{background:#f3f4f6;color:#6b7280}
.person-name{font-weight:600;color:#111}
.affiliation{color:#777;font-size:.85em}
.card-title{margin:5px 0 8px;font-size:.9em;line-height:1.45;color:#222}
.star{color:#f59e0b;margin-right:2px}
.btn-ics{padding:4px 11px;font-size:.79em;background:#fff;border:1px solid #ccc;border-radius:4px;cursor:pointer;color:#555;transition:background .12s,border-color .12s}
.btn-ics:hover{background:#f0f2f5;border-color:#888}
.no-results,.hint{grid-column:1/-1;text-align:center;color:#aaa;padding:48px 16px;font-size:.95em}
</style>
</head>
<body>
<header>
  <h1 id="event-name">Conference Program</h1>
  <div id="event-meta"></div>
  <input type="search" id="search" placeholder="Search by name, session, role…" autocomplete="off" spellcheck="false">
  <div id="result-count"></div>
</header>
<main id="cards"></main>

<script type="application/json" id="data">__DATA__</script>

<script>
(function(){
"use strict";
var data=JSON.parse(document.getElementById('data').textContent);
var sessions=data.sessions||[];
var evMeta={name:data.event_name||'',location:data.event_location||'',tz:data.event_timezone||'UTC'};

document.title=evMeta.name||'Conference Program';
document.getElementById('event-name').textContent=evMeta.name||'Conference Program';
document.getElementById('event-meta').textContent=
  [evMeta.location,evMeta.tz].filter(Boolean).join(' · ');

// ── Token-based fuzzy search ─────────────────────────────────────────────────
// Each space-separated token must prefix-match at least one word in the record.
// "sung hwang", "hwang sung", "s hwang" all match person "Sung Hwang".
function tokenMatch(query,s){
  var tokens=query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  if(!tokens.length)return true;
  var src=[s.person,s.affiliation,s.talk_title,s.session_title,s.session_code,s.role,s.room]
    .filter(Boolean).join(' ').toLowerCase();
  var words=src.split(/[\s,()\-\/\.]+/).filter(Boolean);
  return tokens.every(function(t){
    return words.some(function(w){return w.indexOf(t)===0;});
  });
}

// ── ICS generation ────────────────────────────────────────────────────────────
var MONTHS={jan:1,feb:2,mar:3,apr:4,may:5,jun:6,jul:7,aug:8,sep:9,oct:10,nov:11,dec:12};
var TZ_OFF={
  'Asia/Seoul':540,'Asia/Tokyo':540,'Asia/Shanghai':480,
  'America/Bogota':-300,'America/New_York':-300,'America/Chicago':-360,'America/Los_Angeles':-480,
  'Europe/London':0,'Europe/Paris':60,'Europe/Berlin':60,'UTC':0
};
// VTIMEZONE blocks for known no-DST zones (matches ics_exporter.py)
var VTIMEZONE={
  'Asia/Seoul':'BEGIN:VTIMEZONE\r\nTZID:Asia/Seoul\r\nBEGIN:STANDARD\r\nDTSTART:19700101T000000\r\nTZOFFSETFROM:+0900\r\nTZOFFSETTO:+0900\r\nTZNAME:KST\r\nEND:STANDARD\r\nEND:VTIMEZONE',
  'America/Bogota':'BEGIN:VTIMEZONE\r\nTZID:America/Bogota\r\nBEGIN:STANDARD\r\nDTSTART:19700101T000000\r\nTZOFFSETFROM:-0500\r\nTZOFFSETTO:-0500\r\nTZNAME:COT\r\nEND:STANDARD\r\nEND:VTIMEZONE'
};

function getYear(name){var m=(name||'').match(/\b(20\d{2})\b/);return m?+m[1]:null;}
function pad2(n){return('0'+n).slice(-2);}

function parseDate(ds,yr){
  if(!ds||!yr)return null;
  var m=ds.match(/([A-Za-z]+)\.?\s+(\d{1,2})/);
  if(!m)return null;
  var mo=MONTHS[m[1].toLowerCase().slice(0,3)];
  return mo?[yr,mo,+m[2]]:null;
}

function parseTime(ts){
  if(!ts)return null;
  var m=ts.trim().match(/(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})/);
  return m?[[+m[1],+m[2]],[+m[3],+m[4]]]:null;
}

function toUTCStr(y,mo,d,h,mi,offMin){
  var utcMs=Date.UTC(y,mo-1,d,h,mi,0)-offMin*60000;
  var dt=new Date(utcMs);
  return''+dt.getUTCFullYear()+pad2(dt.getUTCMonth()+1)+pad2(dt.getUTCDate())+
    'T'+pad2(dt.getUTCHours())+pad2(dt.getUTCMinutes())+'00Z';
}

function icsEsc(s){
  return(s||'').replace(/\\/g,'\\\\').replace(/;/g,'\\;').replace(/,/g,'\\,').replace(/\n/g,'\\n');
}

function makeUID(){
  return'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,function(c){
    var r=Math.random()*16|0;return(c==='x'?r:(r&3|8)).toString(16);
  })+'@viewer';
}

// SUMMARY format matches ics_exporter.py:
//   is_primary_author=true  → "★ {talk_title}"
//   chair / discussant      → "[{Role}] {session_code}: {session_title}"
function buildSummary(s){
  if(s.is_primary_author&&s.talk_title){return'★ '+s.talk_title;}
  var role=s.role||'unknown';
  var roleLabel=role.charAt(0).toUpperCase()+role.slice(1);
  var titleParts=[s.session_code,s.session_title].filter(Boolean);
  var title=titleParts.length?titleParts.join(': '):(s.talk_title||'');
  return title?'['+roleLabel+'] '+title:'['+roleLabel+']';
}

function makeICS(s){
  var tz=evMeta.tz;
  var vtblock=VTIMEZONE[tz]||null;
  var yr=getYear(evMeta.name);
  var ymd=parseDate(s.date,yr);
  var times=parseTime(s.time);
  var summary=buildSummary(s);
  var personLine=[s.person,s.affiliation].filter(Boolean).join(' - ');
  var sessLine=[s.session_code,s.session_title].filter(Boolean).join(' - ');
  var descParts=[personLine,sessLine?'Session: '+sessLine:'',s.role?'Role: '+s.role:'',evMeta.name?'Event: '+evMeta.name:''];
  var desc=descParts.filter(Boolean).join('\n');
  var lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Conference Viewer//EN','CALSCALE:GREGORIAN'];
  if(vtblock){lines.push(vtblock);}
  lines.push('BEGIN:VEVENT','UID:'+makeUID());
  if(ymd&&times){
    var y2=ymd[0],mo2=ymd[1],d2=ymd[2];
    var sh=times[0][0],sm=times[0][1],eh=times[1][0],em=times[1][1];
    var localFmt=''+y2+pad2(mo2)+pad2(d2)+'T'+pad2(sh)+pad2(sm)+'00';
    var localEnd=''+y2+pad2(mo2)+pad2(d2)+'T'+pad2(eh)+pad2(em)+'00';
    if(vtblock){
      lines.push('DTSTART;TZID='+tz+':'+localFmt,'DTEND;TZID='+tz+':'+localEnd);
    }else{
      var off=TZ_OFF[tz]!==undefined?TZ_OFF[tz]:0;
      lines.push('DTSTART:'+toUTCStr(y2,mo2,d2,sh,sm,off),'DTEND:'+toUTCStr(y2,mo2,d2,eh,em,off));
    }
  }
  lines.push(
    'SUMMARY:'+icsEsc(summary),
    'LOCATION:'+icsEsc(s.room||''),
    'DESCRIPTION:'+icsEsc(desc),
    'END:VEVENT','END:VCALENDAR'
  );
  return lines.join('\r\n')+'\r\n';
}

// ── Card builder ──────────────────────────────────────────────────────────────
function el(tag,cls,txt){
  var e=document.createElement(tag);
  if(cls)e.className=cls;
  if(txt!==undefined)e.textContent=txt;
  return e;
}

function makeCard(s){
  var role=s.role||'unknown';
  var codeTitle=[s.session_code,s.session_title].filter(Boolean).join(' – ');
  var talk=s.talk_title||'';
  var card=el('div','card card-'+role);

  // Date / time / room badges
  var meta_div=el('div','card-meta');
  [[s.date,'b-date'],[s.time,'b-time'],[s.room,'b-room']].forEach(function(pair){
    if(pair[0]){meta_div.appendChild(el('span','badge '+pair[1],pair[0]));}
  });
  card.appendChild(meta_div);

  // Session code – title
  if(codeTitle){card.appendChild(el('div','card-session',codeTitle));}

  // [ROLE] Person · Affiliation
  var pl=el('div','card-person-line');
  pl.appendChild(el('span','role role-'+role,role.toUpperCase()));
  pl.appendChild(el('span','person-name',s.person||''));
  if(s.affiliation){pl.appendChild(el('span','affiliation',s.affiliation));}
  card.appendChild(pl);

  // ★ Talk title (shown only when talk_title exists)
  if(talk){
    var td=el('div','card-title');
    if(s.is_primary_author){td.appendChild(el('span','star','★'));}
    td.appendChild(document.createTextNode(talk));
    card.appendChild(td);
  }

  // Add to calendar
  var btn=el('button','btn-ics','Add to calendar');
  btn.addEventListener('click',function(){
    var content=makeICS(s);
    var blob=new Blob([content],{type:'text/calendar;charset=utf-8'});
    var url=URL.createObjectURL(blob);
    var a=document.createElement('a');
    a.href=url;
    a.download=[(s.person||'session').replace(/\s+/g,'_'),(s.session_code||'').replace(/\s+/g,'_')]
      .filter(Boolean).join('_')+'.ics';
    document.body.appendChild(a);a.click();
    document.body.removeChild(a);URL.revokeObjectURL(url);
  });
  card.appendChild(btn);
  return card;
}

// ── Render ────────────────────────────────────────────────────────────────────
function render(query){
  var cntEl=document.getElementById('result-count');
  var cardsEl=document.getElementById('cards');
  cardsEl.innerHTML='';

  if(!query){
    cntEl.textContent=sessions.length.toLocaleString()+' sessions loaded — type a name to search';
    cardsEl.appendChild(el('p','hint',
      'e.g. “sung hwang”, “hwang sung”, “s hwang”'));
    return;
  }

  var hits=sessions.filter(function(s){return tokenMatch(query,s);});
  cntEl.textContent=hits.length+' result'+(hits.length!==1?'s':'')+' for “'+query+'”';

  if(!hits.length){
    cardsEl.appendChild(el('p','no-results','No results found.'));
    return;
  }
  hits.forEach(function(s){cardsEl.appendChild(makeCard(s));});
}

var _timer;
document.getElementById('search').addEventListener('input',function(e){
  clearTimeout(_timer);
  _timer=setTimeout(function(){render(e.target.value.trim());},120);
});

render('');
})();
</script>
</body>
</html>
"""


def build(data: dict, output_path: Path) -> None:
    json_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    # Prevent </script> inside JSON from closing the script tag early
    json_str = json_str.replace('</script>', r'<\/script>')
    html = _TEMPLATE.replace('__DATA__', json_str)
    output_path.write_text(html, encoding='utf-8')


def main():
    import argparse
    p = argparse.ArgumentParser(description='Build a standalone viewer.html from sessions.json.')
    p.add_argument('json', metavar='sessions.json', help='Path to sessions.json')
    p.add_argument('output', nargs='?', metavar='output.html',
                   help='Output path (default: same stem as input .html)')
    args = p.parse_args()

    json_path = Path(args.json)
    if not json_path.exists():
        print(f'[error] Not found: {json_path}', file=sys.stderr)
        sys.exit(1)

    data = json.loads(json_path.read_text(encoding='utf-8'))
    out = Path(args.output) if args.output else json_path.with_suffix('.html')
    out.parent.mkdir(parents=True, exist_ok=True)
    build(data, out)
    print(f'-> {out}  ({out.stat().st_size:,} bytes)', file=sys.stderr)


if __name__ == '__main__':
    main()
