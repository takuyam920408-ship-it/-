/**
 * 概要欄に「【楽曲提供：箕輪レコーズ】」と記載されている自分のチャンネルの動画を
 * すべて抽出し、指定のスプレッドシートに URL 一覧として書き出す。
 *
 * ■ 使い方
 *  1. 対象のスプレッドシートを開く
 *     https://docs.google.com/spreadsheets/d/1y9KR9SwZTlKfHr0J8AirIaYC1aT38s6LfxU79qAJy7U/edit
 *  2. 「拡張機能」→「Apps Script」を開く
 *  3. このファイルの中身を丸ごと貼り付けて保存
 *  4. 左メニュー「サービス」→「+」→「YouTube Data API v3」を追加（識別子は YouTube のまま）
 *  5. まず checkChannel を実行して、対象チャンネルが正しいか確認する
 *  6. 問題なければ pickupMinowaRecords を実行する
 *
 *  ※ シートに書かず、一覧テキストだけ欲しい場合は printUrlList を実行する
 */

// ========== 設定 ==========

// 書き出し先スプレッドシート
var SPREADSHEET_ID = '1y9KR9SwZTlKfHr0J8AirIaYC1aT38s6LfxU79qAJy7U';

// 書き出し先シート名（存在しなければ自動作成）
var SHEET_NAME = '箕輪レコーズ';

// 対象チャンネルID。
// 空文字のままなら「スクリプトを実行している Google アカウント自身のチャンネル」を使う。
// ブランドアカウントで checkChannel が別のチャンネルを指した場合は、
// ここに UCxxxxxxxx... 形式のチャンネルIDを直接書く。
var CHANNEL_ID = '';

// 概要欄の判定条件。
// 全角／半角コロン、括弧の有無、前後の空白のゆらぎを吸収する。
// 厳密に【楽曲提供：箕輪レコーズ】だけに限定したい場合は /【楽曲提供：箕輪レコーズ】/ に変更する。
var MATCH_PATTERN = /楽曲提供\s*[：:]\s*箕輪レコーズ/;

// ========== 事前確認 ==========

/**
 * 対象チャンネルが意図どおりか確認する。
 * 実行後、メニュー「実行数」またはログ表示で結果を見る。
 */
function checkChannel() {
  var params = CHANNEL_ID ? { id: CHANNEL_ID } : { mine: true };
  var res = YouTube.Channels.list('snippet,contentDetails,statistics', params);

  if (!res.items || res.items.length === 0) {
    throw new Error(
      'チャンネルが取得できませんでした。\n' +
      '・実行中の Google アカウントを確認してください\n' +
      '・ブランドアカウントの場合は CHANNEL_ID に直接チャンネルIDを設定してください'
    );
  }

  var ch = res.items[0];
  Logger.log('チャンネル名: ' + ch.snippet.title);
  Logger.log('チャンネルID: ' + ch.id);
  Logger.log('公開動画数: ' + ch.statistics.videoCount + '本');
  Logger.log('');
  Logger.log('↑ これが対象のチャンネルで合っていれば pickupMinowaRecords を実行してください。');
  Logger.log('違う場合は CHANNEL_ID に上記とは別の正しいチャンネルIDを設定してください。');
}

// ========== メイン処理 ==========

function pickupMinowaRecords() {
  var videos = fetchAllUploads_();
  var matched = videos.filter(function (v) {
    return MATCH_PATTERN.test(v.description || '');
  });

  matched.sort(function (a, b) {
    return b.publishedAt.localeCompare(a.publishedAt); // 新しい順
  });

  writeToSheet_(matched, videos.length);

  Logger.log('チャンネル内の動画: ' + videos.length + '本');
  Logger.log('該当した動画: ' + matched.length + '本');

  if (matched.length > 0) {
    Logger.log('');
    Logger.log(buildCopyBlock_(matched));
  }

  // 1本も引っかからなかった場合、表記ゆれを疑えるよう実物の概要欄を出す
  if (matched.length === 0 && videos.length > 0) {
    Logger.log('');
    Logger.log('--- 該当ゼロでした。概要欄の実際の表記を確認してください ---');
    videos.slice(0, 3).forEach(function (v) {
      Logger.log('[' + v.title + ']');
      Logger.log((v.description || '(概要欄なし)').slice(0, 300));
      Logger.log('---');
    });
  }
}

/**
 * 対象チャンネルのアップロード動画をすべて取得する。
 * playlistItems の description は省略されることがあるため、
 * videos.list で概要欄の全文を取り直している。
 */
function fetchAllUploads_() {
  var params = CHANNEL_ID ? { id: CHANNEL_ID } : { mine: true };
  var channels = YouTube.Channels.list('contentDetails', params);
  if (!channels.items || channels.items.length === 0) {
    throw new Error('チャンネルが取得できませんでした。先に checkChannel を実行して確認してください。');
  }
  var uploadsPlaylistId = channels.items[0].contentDetails.relatedPlaylists.uploads;

  // 1) アップロード再生リストから videoId を全件収集
  var videoIds = [];
  var pageToken = null;
  do {
    var page = YouTube.PlaylistItems.list('contentDetails', {
      playlistId: uploadsPlaylistId,
      maxResults: 50,
      pageToken: pageToken
    });
    (page.items || []).forEach(function (item) {
      videoIds.push(item.contentDetails.videoId);
    });
    pageToken = page.nextPageToken;
  } while (pageToken);

  // 2) 50件ずつ videos.list で概要欄の全文を取得
  var videos = [];
  for (var i = 0; i < videoIds.length; i += 50) {
    var chunk = videoIds.slice(i, i + 50);
    var res = YouTube.Videos.list('snippet', { id: chunk.join(',') });
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

function writeToSheet_(matched, totalCount) {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sheet = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
  sheet.clear();

  var header = ['No.', '動画URL', 'タイトル', '公開日'];
  var rows = matched.map(function (v, i) {
    return [
      i + 1,
      'https://www.youtube.com/watch?v=' + v.id,
      v.title,
      Utilities.formatDate(new Date(v.publishedAt), 'Asia/Tokyo', 'yyyy/MM/dd')
    ];
  });

  sheet.getRange(1, 1, 1, header.length).setValues([header]).setFontWeight('bold');
  if (rows.length > 0) {
    sheet.getRange(2, 1, rows.length, header.length).setValues(rows);
  }

  var note = '【楽曲提供：箕輪レコーズ】該当 ' + matched.length + '本 / 全 ' + totalCount + '本'
    + '（更新: ' + Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy/MM/dd HH:mm') + '）';
  sheet.getRange(rows.length + 3, 1).setValue(note);

  sheet.setFrozenRows(1);
  sheet.autoResizeColumns(1, header.length);
}

// ========== コピー用テキスト出力 ==========

/**
 * シートには書かず、該当動画の一覧をログにテキストで出すだけの関数。
 * ログの内容をそのままコピーして貼り付けられる。
 */
function printUrlList() {
  var videos = fetchAllUploads_();
  var matched = videos.filter(function (v) {
    return MATCH_PATTERN.test(v.description || '');
  });

  matched.sort(function (a, b) {
    return b.publishedAt.localeCompare(a.publishedAt);
  });

  Logger.log('チャンネル内の動画: ' + videos.length + '本');
  Logger.log('該当した動画: ' + matched.length + '本');
  Logger.log('');

  if (matched.length === 0) {
    Logger.log('--- 該当ゼロでした。概要欄の実際の表記を確認してください ---');
    videos.slice(0, 3).forEach(function (v) {
      Logger.log('[' + v.title + ']');
      Logger.log((v.description || '(概要欄なし)').slice(0, 300));
      Logger.log('---');
    });
    return;
  }

  Logger.log(buildCopyBlock_(matched));
}

/**
 * 「公開日<TAB>タイトル<TAB>URL」形式の一行データを組み立てる。
 * タブ区切りなので、そのままスプレッドシートにも貼り付けられる。
 */
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
