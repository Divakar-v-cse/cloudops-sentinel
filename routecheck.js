(() => {
  const t = (document.body.innerText || '');
  const patterns = [
    'Something went wrong',
    'Failed to fetch',
    'failed to fetch',
    'Error boundary',
    'Uncaught',
    'NetworkError',
    'Request failed',
    'is not defined',
    'Cannot read',
    '500',
    '401',
    '403',
    'Failed to load',
    'An error occurred'
  ];
  const hits = patterns.filter(p => t.includes(p));
  const main = document.querySelector('main') || document.body;
  const mainText = (main.innerText || '');
  return {
    url: location.href,
    title: document.title,
    bodyTextLen: t.length,
    mainTextLen: mainText.length,
    hits: hits,
    mainHead: mainText.slice(0, 260).replace(/\n{2,}/g, ' | '),
    headings: Array.from(document.querySelectorAll('h1,h2')).slice(0, 8).map(h => h.innerText.trim()).filter(Boolean),
    tables: document.querySelectorAll('main table').length,
    svgs: document.querySelectorAll('main svg').length,
    buttons: document.querySelectorAll('main button').length
  };
})()
