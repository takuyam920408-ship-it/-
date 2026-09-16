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
 *  5. 関数 pickupMinowaRecords を実行し、初回の権限承認を許可する
 *
 *  ※ スクリプトを実行する Google アカウントが、対象 YouTube チャンネルの
 *    オーナー（またはチャンネル切り替え済みのアカウント）である必要があります。
 */

// 書き出し先スプレッドシート
var SPREADSHEET_ID = '1y9KR9SwZTlKfHr0J8AirIaYC1aT38s6LfxU79qAJy7U';

// 書き出し先シート名（存在しなければ自動作成）
var SHEET_NAME = '箕輪レコーズ';

// 概要欄の判定条件。
// 全角／半角コロン、括弧の有無、前後の空白のゆらぎを吸収する。
var MATCH_PATTERN = /楽曲提供\s*[：:]\s*箕輪レコーズ/;

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
}

/**
 * 自分のチャンネルのアップロード動画をすべて取得する。
 * playlistItems の description は省略されることがあるため、
 * videos.list で概要欄の全文を取り直している。
 */
function fetchAllUploads_() {
  var channels = YouTube.Channels.list('contentDetails', { mine: true });
  if (!channels.items || channels.items.length === 0) {
    throw new Error('チャンネルが取得できませんでした。実行中の Google アカウントを確認してください。');
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
