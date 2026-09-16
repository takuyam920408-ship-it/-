/**
 * 「【楽曲提供：箕輪レコーズ】」と記載されている自分のチャンネルの動画を抽出し、
 * 指定のスプレッドシートに URL 一覧として書き出す。
 *
 * このバージョンは Apps Script の「サービス」追加を必要としない。
 * YouTube Data API を UrlFetchApp で直接呼び、認可は appsscript.json の
 * oauthScopes で宣言する。
 *
 * ■ 事前準備（appsscript.json の編集が必須）
 *  1. 左メニューの歯車「プロジェクトの設定」を開く
 *  2. 「"appsscript.json" マニフェスト ファイルをエディタで表示する」にチェック
 *  3. 左メニュー「エディタ」に戻ると appsscript.json が現れるので、その中身を
 *     README または案内の JSON で丸ごと置き換えて保存する
 */

// ========== 設定 ==========

var SPREADSHEET_ID = '1y9KR9SwZTlKfHr0J8AirIaYC1aT38s6LfxU79qAJy7U';
var SHEET_GID = 2005983596;
var START_CELL = 'A1';
var CLEAR_BEFORE_WRITE = true;
var CHANNEL_ID = '';
var MATCH_PATTERN = /楽曲提供\s*[：:]\s*箕輪レコーズ/;

// ========== 事前確認 ==========

function checkChannel() {
  var params = CHANNEL_ID ? { id: CHANNEL_ID } : { mine: true };
  params.part = 'snippet,contentDetails,statistics';
  var res = ytApi_('channels', params);

  if (!res.items || res.items.length === 0) {
    throw new Error('チャンネルが取得できませんでした。CHANNEL_ID の設定を確認してください。');
  }

  var ch = res.items[0];
  Logger.log('チャンネル名: ' + ch.snippet.title);
  Logger.log('チャンネルID: ' + ch.id);
  Logger.log('公開動画数: ' + ch.statistics.videoCount + '本');
}

// ========== メイン ==========

function pickupMinowaRecords() {
  var videos = fetchAllUploads_();
  var matched = filterMatched_(videos);

  writeToSheet_(matched, videos.length);

  Logger.log('チャンネル内の動画: ' + videos.length + '本');
  Logger.log('該当した動画: ' + matched.length + '本');

  if (matched.length > 0) {
    Logger.log('');
    Logger.log(buildCopyBlock_(matched));
  } else if (videos.length > 0) {
    logSamples_(videos);
  }
}

function printUrlList() {
  var videos = fetchAllUploads_();
  var matched = filterMatched_(videos);

  Logger.log('チャンネル内の動画: ' + videos.length + '本');
  Logger.log('該当した動画: ' + matched.length + '本');
  Logger.log('');

  if (matched.length === 0) {
    logSamples_(videos);
    return;
  }

  Logger.log(buildCopyBlock_(matched));
}

// ========== 内部処理 ==========

/**
 * YouTube Data API をアクセストークン付きで直接呼ぶ。
 * 「サービス」に YouTube Data API v3 を追加していなくても動作する。
 */
function ytApi_(path, params) {
  var url = 'https://www.googleapis.com/youtube/v3/' + path + '?' + toQuery_(params);
  var res = UrlFetchApp.fetch(url, {
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    muteHttpExceptions: true
  });

  var code = res.getResponseCode();
  var body = res.getContentText();

  if (code !== 200) {
    throw new Error(
      'YouTube API エラー (HTTP ' + code + ')\n' + body + '\n\n' +
      '403 の場合は appsscript.json の oauthScopes 設定を確認してください。'
    );
  }
  return JSON.parse(body);
}

function toQuery_(params) {
  var parts = [];
  for (var k in params) {
    var v = params[k];
    if (v === null || v === undefined || v === '') continue;
    parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
  }
  return parts.join('&');
}

function filterMatched_(videos) {
  var matched = videos.filter(function (v) {
    return MATCH_PATTERN.test(v.description || '') || MATCH_PATTERN.test(v.title || '');
  });
  matched.sort(function (a, b) {
    return b.publishedAt.localeCompare(a.publishedAt);
  });
  return matched;
}

function fetchAllUploads_() {
  var params = CHANNEL_ID ? { id: CHANNEL_ID } : { mine: true };
  params.part = 'contentDetails';
  var channels = ytApi_('channels', params);

  if (!channels.items || channels.items.length === 0) {
    throw new Error('チャンネルが取得できませんでした。先に checkChannel を実行してください。');
  }
  var uploadsPlaylistId = channels.items[0].contentDetails.relatedPlaylists.uploads;

  var videoIds = [];
  var pageToken = null;
  do {
    var page = ytApi_('playlistItems', {
      part: 'contentDetails',
      playlistId: uploadsPlaylistId,
      maxResults: 50,
      pageToken: pageToken
    });
    (page.items || []).forEach(function (item) {
      videoIds.push(item.contentDetails.videoId);
    });
    pageToken = page.nextPageToken;
  } while (pageToken);

  var videos = [];
  for (var i = 0; i < videoIds.length; i += 50) {
    var res = ytApi_('videos', {
      part: 'snippet',
      id: videoIds.slice(i, i + 50).join(',')
    });
    (res.items || []).forEach(function (v) {
      videos.push({
        id: v.id,
        title: v.snippet.title,
        description: v.snippet.description,
        publishedAt: v.snippet.publishedAt
      });
    });
  }

  return videos;
}

function logSamples_(videos) {
  Logger.log('--- 該当ゼロでした。実際の表記を確認してください ---');
  videos.slice(0, 3).forEach(function (v) {
    Logger.log('[' + v.title + ']');
    Logger.log((v.description || '(概要欄なし)').slice(0, 300));
    Logger.log('---');
  });
}

function writeToSheet_(matched, totalCount) {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sheet = getSheetByGid_(ss, SHEET_GID);

  if (CLEAR_BEFORE_WRITE) {
    sheet.clear();
  }

  var anchor = sheet.getRange(START_CELL);
  var row0 = anchor.getRow();
  var col0 = anchor.getColumn();

  var header = ['No.', '動画URL', 'タイトル', '公開日'];
  var rows = matched.map(function (v, i) {
    return [
      i + 1,
      'https://www.youtube.com/watch?v=' + v.id,
      v.title,
      Utilities.formatDate(new Date(v.publishedAt), 'Asia/Tokyo', 'yyyy/MM/dd')
    ];
  });

  sheet.getRange(row0, col0, 1, header.length).setValues([header]).setFontWeight('bold');
  if (rows.length > 0) {
    sheet.getRange(row0 + 1, col0, rows.length, header.length).setValues(rows);
  }

  var note = '【楽曲提供：箕輪レコーズ】該当 ' + matched.length + '本 / 全 ' + totalCount + '本'
    + '（更新: ' + Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy/MM/dd HH:mm') + '）';
  sheet.getRange(row0 + rows.length + 2, col0).setValue(note);

  if (row0 === 1) {
    sheet.setFrozenRows(1);
  }
  sheet.autoResizeColumns(col0, header.length);

  Logger.log('書き込み先タブ: ' + sheet.getName() + '（gid: ' + sheet.getSheetId() + '）');
}

function getSheetByGid_(ss, gid) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() === gid) {
      return sheets[i];
    }
  }
  throw new Error('gid ' + gid + ' のタブが見つかりません。');
}

function buildCopyBlock_(matched) {
  var lines = ['===== ここから下をコピー ====='];
  matched.forEach(function (v) {
    lines.push([
      Utilities.formatDate(new Date(v.publishedAt), 'Asia/Tokyo', 'yyyy/MM/dd'),
      v.title.replace(/[\t\r\n]+/g, ' '),
      'https://www.youtube.com/watch?v=' + v.id
    ].join('\t'));
  });
  lines.push('===== ここまで =====');
  return lines.join('\n');
}
