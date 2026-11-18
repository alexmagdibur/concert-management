const icons = {
  grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4m8-4v4m-8 7h2m4 0h2m-8 3h2"/>',
  pin:'<path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>',
  people:'<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2m1-15a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 4v2"/>',
  tag:'<path d="M3 4h8l10 10-7 7L4 11Z"/><circle cx="8" cy="8" r="1"/>',
  wallet:'<path d="M3 8h17a1 1 0 0 1 1 1v10H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h13m3 7h-5v4h5"/>',
  report:'<path d="M5 3h10l4 4v14H5zM15 3v5h4M8 12h8m-8 4h8"/>',
  chart:'<path d="M4 4v16h17M8 15l4-4 3 2 5-6"/>',
  shield:'<path d="M12 3l8 3v5c0 5-4 8-8 10-4-2-8-5-8-10V6zM9 12l2 2 4-5"/>',
  screen:'<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M12 17v4m-4 0h8"/>',
  login:'<path d="M14 4h6v16h-6m-3-12 4 4-4 4m4-4H3"/>',
  plus:'<path d="M12 5v14M5 12h14"/>', arrow:'<path d="M4 12h15m-6-6 6 6-6 6"/>',
  down:'<path d="M6 5v13m-3-3 3 3 3-3m4-7h8m-8 4h6m-6 4h4"/>',
  up:'<path d="M6 18V5m-3 3 3-3 3 3m4 0h8m-8 4h6m-6 4h4"/>',
};
const icon = (name) => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+icons[name]+'</svg>';
const groups = [
 ['Планирование',[['overview','Обзор','grid'],['concerts','Концерты','calendar'],['venues','Площадки','pin'],['parties','Контрагенты','people']]],
 ['Финансы',[['journal','Финансовый журнал','wallet'],['categories','Категории операций','tag'],['reports','Отчёты','report'],['analytics','Аналитика','chart']]],
 ['Администрирование',[['users','Пользователи','shield']]]
];
const titles = Object.fromEntries(groups.flatMap(([,entries]) => entries).map(([key,title]) => [key,title]));
const labels = {confirmed:'Подтверждён',pending:'На согласовании',done:'Проведён',off:'Отменён'};
const events = [
 {id:1,name:'Вечерний концерт', day:'21 ноя', date:'21 ноября', time:'19:30', venue:'Стадион «Лужники»', city:'Москва', status:'confirmed', budget:780000},
 {id:2,name:'Акустическая программа',day:'27 ноя',date:'27 ноября',time:'20:00',venue:'Городской концертный зал',city:'Казань',status:'pending',budget:420000},
 {id:3,name:'Зимняя программа',day:'04 дек',date:'4 декабря',time:'19:00',venue:'Большой зал',city:'Санкт-Петербург',status:'pending',budget:610000},
 {id:4,name:'Осенняя программа',day:'16 ноя',date:'16 ноября',time:'18:30',venue:'Большой зал',city:'Санкт-Петербург',status:'done',budget:480000},
];
const incoming=[56,96,62,144,105,185,132], out=[25,51,34,61,55,93,64];
const amount = (n) => new Intl.NumberFormat('ru-RU').format(n)+' ₽';
const sum = (arr) => arr.reduce((a,b)=>a+b,0)*1000;
const badge = (text, kind='') => '<span class="badge '+kind+'">'+text+'</span>';
const concertBadge = (event) => badge(labels[event.status], ({pending:'wait',done:'done',off:'off'})[event.status]||'');
const button = (text, key, iconName, primary=false) => '<button class="btn'+(primary?' primary':'')+'" data-dialog="'+key+'" type="button">'+(iconName?icon(iconName):'')+text+'</button>';
const link = (text, path, iconName) => '<a class="btn" href="#'+path+'">'+text+(iconName?icon(iconName):'')+'</a>';
const title = (name, sub, actions='',tag='') => '<div class="page-title" data-enter><div>'+(tag?'<div class="eyebrow">'+tag+'</div>':'')+'<h1>'+name+'</h1>'+(sub?'<p>'+sub+'</p>':'')+'</div>'+(actions?'<div class="page-tools">'+actions+'</div>':'')+'</div>';
const head = (name, sub='', action='') => '<div class="card-head"><div><h2>'+name+'</h2>'+(sub?'<p>'+sub+'</p>':'')+'</div>'+action+'</div>';
const table = (columns, rows, label=columns.join(', ')) => '<div class="table-wrap" tabindex="0" role="region" aria-label="'+label+'"><table><thead><tr>'+columns.map((column)=>'<th scope="col">'+column+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(cell=>'<td>'+cell+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';
const metric = (label, value, note, sym) => '<article class="metric"><span>'+label+'</span><b>'+value+'</b><small>'+note+'</small><span class="metric-icon">'+icon(sym)+'</span></article>';
const metrics = () => '<div class="metrics">'+metric('Поступления',amount(sum(incoming)),'Учтено за неделю','down')+metric('Расходы',amount(sum(out)),'Учтено за неделю','up')+metric('Денежный результат',amount(sum(incoming)-sum(out)),'Поступления минус расходы','chart')+'</div>';
const eventRows = (list) => list.map(event=>['<a class="row-link" href="#concert/'+event.id+'">'+event.name+'</a><span class="sub">'+event.city+' · '+event.venue+'</span>','<span class="num">'+event.day+'</span><span class="sub">'+event.time+'</span>',concertBadge(event)]);
const renderChart = () => '<div class="chart-legend"><span class="legend"><i class="dot"></i> Поступления</span><span class="legend"><i class="dot out"></i> Расходы</span></div><div class="chart" role="img" aria-label="График по дням. '+incoming.map((n,i)=>(16+i)+' ноября: поступления '+n+' тыс. рублей, расходы '+out[i]+' тыс. рублей').join('; ')+'"><div class="chart-axis"><span>210 тыс.</span><span>140 тыс.</span><span>70 тыс.</span><span>0</span></div><div class="chart-body">'+incoming.map((n,i)=>'<div class="chart-day"><div class="chart-bars"><span class="bar" style="--value:'+n/2.1+'" title="'+amount(n*1000)+'"></span><span class="bar out" style="--value:'+out[i]/2.1+'" title="'+amount(out[i]*1000)+'"></span></div><b>'+(16+i)+' ноя</b></div>').join('')+'</div></div>';
const overview = () => title('Обзор концертов','Календарь и учтённые операции за неделю.',button('Новый концерт','newConcert','plus',true),'16–22 ноября 2026')+metrics()+
 '<div class="overview-grid"><div><section class="card">'+head('Движение средств','По датам операций',link('К отчёту','reports','arrow'))+renderChart()+'</section><section class="card">'+head('Концерты','Ближайшие и проведённые',link('Список','concerts','arrow'))+table(['Концерт','Дата','Статус'],eventRows(events.slice(0,3)))+
 '</section></div><div><section class="feature" data-visual data-enter><div class="eyebrow">Ближайший концерт</div><div class="feature-inner"><div class="daytile"><strong>21</strong><small>НОЯ</small></div><div><h2>Вечерний концерт</h2><p>Стадион «Лужники» · 19:30</p></div></div>'+badge('Подтверждён')+'<div>'+link('Открыть концерт','concert/1','arrow')+'</div></section><section class="card">'+head('Повестка')+
 events.slice(0,3).map(e=>'<a class="agenda-item" href="#concert/'+e.id+'"><i class="dot"></i><div><strong>'+e.name+'</strong><small>'+e.city+'</small></div><time>'+e.day+'</time></a>').join('')+'</section></div></div>';
const filterBar = (options) => '<div class="toolbar"><label class="field">Поиск<input type="search" id="list-search" autocomplete="off"></label>'+(options?'<label class="field">Статус<select id="status-filter"><option value="">Все</option>'+options+'</select></label>':'')+'</div>';
const concerts = () => title('Концерты','Расписание, площадки и договоры.',button('Новый концерт','newConcert','plus',true))+
 '<section class="card">'+filterBar(Object.entries(labels).map(([value,label])=>'<option value="'+value+'">'+label+'</option>').join(''))+
 '<div id="list-body" aria-live="polite">'+table(['Концерт','Дата','Статус'],eventRows(events))+'</div></section>';
const catalogs = {
 venues:{title:'Площадки',text:'Залы и адреса для концертного расписания.',action:'Новая площадка',key:'venue', columns:['Название','Город','Тип'],rows:[['Стадион «Лужники»','Москва','Стадион'],['Городской концертный зал','Казань','Зал'],['Большой зал','Санкт-Петербург','Зал']]},
 parties:{title:'Контрагенты',text:'Организаторы и подрядчики.',action:'Новый контрагент',key:'party',columns:['Название','Тип','Назначение'],rows:[['Организатор программы','Юридическое лицо','Организация концертов'],['Сценическая команда','Юридическое лицо','Монтаж и оборудование'],['Транспортный подрядчик','ИП','Перевозка оборудования']]},
 categories:{title:'Категории операций',text:'Назначение и направление операций журнала.',action:'Новая категория',key:'category',columns:['Код','Название','Направление'],rows:[['FEE','Гонорар','Поступление'],['RENT','Аренда площадки','Расход'],['TRANSPORT','Транспорт','Расход']]},
 users:{title:'Пользователи',text:'Роли и доступ к рабочему пространству.',action:'Новый пользователь',key:'user',columns:['Сотрудник','Роль','Доступ'],rows:[['Менеджер тура','MANAGER','Активен'],['Администратор','ADMIN','Активен']]},
};
function catalog(key){const d=catalogs[key];return title(d.title,d.text,button(d.action,d.key,'plus',true))+
 '<section class="card">'+filterBar()+'<div id="list-body" aria-live="polite">'+table(d.columns,d.rows)+'</div></section>';}
const facts = (...items) => '<dl class="facts">'+items.map(([term,content])=>'<div><dt>'+term+'</dt><dd>'+content+'</dd></div>').join('')+'</dl>';
const transactions = [
 ['18 ноя 2026','Гонорар за выступление','Концертный гонорар','+150 000 ₽',badge('Учтена','done')],
 ['18 ноя 2026','Перевозка оборудования','Транспорт','−40 000 ₽',badge('Учтена','done')],
 ['17 ноя 2026','Резервный комплект','Оборудование','−12 000 ₽',badge('Черновик','off')],
];
const journal = () => title('Финансовый журнал','Поступления, расходы и возвраты.',button('Новая операция','operation','plus',true))+
 '<section class="card">'+head('Операции')+table(['Дата','Основание','Категория','Сумма','Статус'],transactions)+'</section>';
const reports = () => title('Финансовый отчёт','Вечерний концерт · ноябрь 2026',link('К концерту','concert/1','arrow'))+
 '<div class="metrics">'+metric('Поступления','150 000 ₽','Учтённый гонорар','down')+metric('Расходы','40 000 ₽','Учтённые расходы','up')+metric('Денежный результат','110 000 ₽','За выбранный период','chart')+
 '</div><section class="card">'+head('Расчёты по договору')+facts(['Сумма договора','500 000 ₽'],['Чистая оплата','150 000 ₽'],['Остаток','350 000 ₽'],['Срез','30 ноября 2026'])+
 '</section><section class="card">'+head('Детализация')+table(['Дата','Основание','Категория','Сумма','Статус'],transactions.slice(0,2))+'</section>';
const analytics = () => title('Аналитика','Результаты проведённых концертов и прогноз расходов.')+
 '<div class="splits"><section class="card">'+head('Рейтинг концертов')+table(['Концерт','Результат'],[['Осенняя программа','110 000 ₽'],['Летняя программа','79 000 ₽'],['Камерный концерт','−9 000 ₽']])+
 '</section><section class="card">'+head('Прогноз расходов','Зимняя программа')+facts(['Ожидаемые расходы','550 000 ₽'],['Наблюдения','10'],['95%-й интервал среднего','333 410–766 590 ₽'])+
 '<p class="muted-line">Интервал описывает оценку среднего расхода.</p></section></div>';
function concert(id,tab='general'){
 const e=events.find(row=>row.id===Number(id))||events[0];
 const tabs=[['general','Общее'],['contract','Договоры'],['engagement','Подрядчики'],['cash','Финансы']];
 const panels={
 general:'<div class="splits"><section class="card">'+head('Детали концерта')+facts(['Начало',e.date+' · '+e.time],['Площадка',e.venue],['Город',e.city],['Плановый бюджет',amount(e.budget)])+'</section><section class="card">'+head('Состояние')+concertBadge(e)+'<p class="muted-line">Основной договор и ответственный менеджер указаны в карточке.</p>'+link('К финансовому отчёту','reports','arrow')+'</section></div>',
 contract:'<section class="card">'+head('Договоры','Договоры концерта',button('Новый договор','contract','plus',true))+table(['Номер','Назначение','Сумма','Статус'],[['SHOW-001','Основной договор','500 000 ₽',badge('Действует','done')],['SERVICE-001','Транспорт','40 000 ₽',badge('Черновик','off')]])+'</section>',
 engagement:'<section class="card">'+head('Работы подрядчиков','',button('Добавить работу','engagement','plus',true))+table(['Работа','Срок','Сумма','Статус'],[['Перевозка оборудования','20 ноя','40 000 ₽',badge('Согласовано','done')],['Монтаж сцены','21 ноя','64 000 ₽',badge('Планируется','wait')]])+'</section>',
 cash:'<section class="card">'+head('Операции концерта','',button('Новая операция','operation','plus',true))+table(['Дата','Основание','Категория','Сумма','Статус'],transactions)+'</section>',
 };
 return title(e.name,e.city+' · '+e.date,link('Все концерты','concerts'), 'Карточка концерта')+
 '<nav class="tabs" aria-label="Карточка концерта">'+tabs.map(([k,label])=>'<a class="btn" href="#concert/'+e.id+'/'+k+'" '+(tab===k?'aria-current="page"':'')+'>'+label+'</a>').join('')+'</nav>'+(panels[tab]||panels.general);
}
const login = () => '<div class="login-preview">'+title('Вход в Concert CRM','Рабочее пространство менеджера')+
 '<section class="card">'+head('Учётная запись')+'<div class="dialog-fields"><label class="field">Логин<input type="text" disabled></label><label class="field">Пароль<input type="password" disabled></label>'+link('К обзору','overview','arrow')+'</div></section></div>';
const forms={
 newConcert:['Новый концерт',[['Название','text'],['Начало','datetime-local'],['Площадка','text'],['Организатор','text'],['Плановый бюджет','number']]],
 venue:['Новая площадка',[['Название','text'],['Город','text'],['Адрес','text'],['Вместимость','number']]],
 party:['Новый контрагент',[['Название','text'],['Тип','text'],['Примечания','text']]],
 category:['Новая категория',[['Код','text'],['Название','text'],['Направление','select',['Поступление','Расход']]]],
 user:['Новый пользователь',[['ФИО','text'],['Логин','text'],['Роль','select',['Менеджер','Администратор']]]],
 operation:['Новая операция',[['Дата','date'],['Сумма','number'],['Направление','select',['Поступление','Расход']],['Основание','text']]],
 contract:['Новый договор',[['Номер','text'],['Дата подписания','date'],['Сумма','number'],['Предмет','text']]],
 engagement:['Новая работа',[['Подрядчик','text'],['Описание работы','text'],['Срок','datetime-local']]],
};
const screen=document.querySelector('#screen'), nav=document.querySelector('#navigation'), dialog=document.querySelector('#dialog');
const theme=document.querySelector('#theme'), menu=document.querySelector('#toggle-menu'), sidebar=document.querySelector('#sidebar');
document.querySelector('#login-icon').innerHTML=icon('login');document.querySelector('#theme-icon').innerHTML=icon('screen');
try{theme.value=localStorage.getItem('concert-preview-theme')||'system'}catch{}
const requestedTheme = new URLSearchParams(location.search).get('theme');
if(['light','dark','system'].includes(requestedTheme))theme.value=requestedTheme;
if(!theme.value)theme.value='system';
function setTheme(){document.documentElement.dataset.theme=theme.value;try{localStorage.setItem('concert-preview-theme',theme.value)}catch{}}
setTheme();theme.addEventListener('change',setTheme);
function closeMenu(){sidebar.classList.remove('open');menu.setAttribute('aria-expanded','false');menu.setAttribute('aria-label','Открыть меню')}
document.querySelector('#close-menu').addEventListener('click',()=>{closeMenu();menu.focus()});
menu.addEventListener('click',()=>{if(sidebar.classList.contains('open'))closeMenu();else{sidebar.classList.add('open');menu.setAttribute('aria-expanded','true');menu.setAttribute('aria-label','Закрыть меню');document.querySelector('#close-menu').focus()}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&sidebar.classList.contains('open')){closeMenu();menu.focus()}});
screen.addEventListener('click',(event)=>{
 const key=event.target.closest('[data-dialog]')?.dataset.dialog;if(!forms[key])return;
 const [name,fields]=forms[key];dialog.setAttribute('aria-label',name);
 document.querySelector('#dialog-content').innerHTML='<h2>'+name+'</h2><div class="dialog-fields">'+
 fields.map(([label,type,values])=>'<label class="field">'+label+(values?'<select>'+values.map(v=>'<option>'+v+'</option>').join('')+'</select>':'<input type="'+type+'">')+'</label>').join('')+
 '<form method="dialog"><button class="btn primary">Закрыть форму</button></form></div>';
 dialog.showModal();
});
function bindFilter(key){
 const search=document.querySelector('#list-search'), status=document.querySelector('#status-filter'), target=document.querySelector('#list-body');if(!search||!target)return;
 const filter=()=>{
   const query=search.value.trim().toLocaleLowerCase('ru');
   if(key==='concerts'){const rows=events.filter(e=>[e.name,e.city,e.venue].some(x=>x.toLocaleLowerCase('ru').includes(query))&&(!status.value||e.status===status.value));target.innerHTML=rows.length?table(['Концерт','Дата','Статус'],eventRows(rows)):'<p class="muted-line">Концерты не найдены.</p>';}
   else {const {rows,columns}=catalogs[key], filtered=rows.filter(row=>row.some(x=>x.toLocaleLowerCase('ru').includes(query)));target.innerHTML=filtered.length?table(columns,filtered):'<p class="muted-line">Записи не найдены.</p>';}
 };
 search.addEventListener('input',filter);status?.addEventListener('change',filter);
}
function render(){
 const hash=location.hash.slice(1);if(hash==='main-content')return;
 const [route,id,tab]=hash.split('/');
 const key=route==='concert'?'concerts':Object.hasOwn(titles,route)?route:route==='login'?'login':'overview';
 nav.innerHTML=groups.map(([group,entries])=>'<div class="navgroup"><div class="navtitle">'+group+'</div>'+entries.map(([path,label,symbol])=>'<a class="navlink" href="#'+path+'" '+(path===key?'aria-current="page"':'')+'>'+icon(symbol)+label+'</a>').join('')+'</div>').join('');
 document.querySelector('#crumb').textContent=key==='login'?'Вход':titles[key];
 const screens={overview,concerts,journal,reports,analytics,login};
 screen.innerHTML=(route==='concert'?concert(id,tab):screens[key]?screens[key]():catalog(key))+'<p class="footnote">Концепция интерфейса · Демонстрационные данные</p>';
 bindFilter(key);closeMenu();window.scrollTo(0,0);
}
window.addEventListener('hashchange',render);render();
