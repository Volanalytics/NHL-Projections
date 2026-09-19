/**
 * IntelligenceExport.gs
 * Read-only NHL projection snapshot for the external Intelligence pipeline.
 * Does not alter model/projection cells.
 *
 * Run: exportNhlIntelligenceSnapshot()
 * Output: JSON file in Google Drive (folder optional via Script Property
 * NHL_INTELLIGENCE_FOLDER_ID). The function also returns the JSON string.
 */

function exportNhlIntelligenceSnapshot() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  SpreadsheetApp.flush();

  const now = new Date();
  const tz = ss.getSpreadsheetTimeZone() || Session.getScriptTimeZone() || 'America/Chicago';
  const slateDate = (typeof getSlateDate_ === 'function')
    ? getSlateDate_()
    : Utilities.formatDate(now, tz, 'yyyy-MM-dd');

  const lineups = readSheetObjects_(ss, sheetName_('LINEUPS', 'Lineups'));
  const matchup = readSheetObjects_(ss, sheetName_('MATCHUP', 'Matchup'));
  const projections = readSheetObjects_(ss, sheetName_('PROJECTIONS', 'Projections'));
  const summary = readSheetObjects_(ss, sheetName_('GAME_SUMMARY', 'Game_Summary'));
  const review = readSheetObjects_(ss, sheetName_('MATCH_REVIEW', 'Match_Review'), true);
  const runLog = readSheetObjects_(ss, sheetName_('LOG', 'Run_Log'), true);

  const conflicts = buildModelConflicts_(lineups, matchup, projections, summary, review);
  const snapshot = {
    schema_version: '1.0',
    generated_at: now.toISOString(),
    slate_date: String(slateDate),
    projection_source: {
      system: 'Google Sheets',
      spreadsheet_id: ss.getId(),
      spreadsheet_name: ss.getName(),
      snapshot_at: now.toISOString(),
      immutable: true
    },
    pipeline: buildPipelineStatus_(runLog, now),
    games: buildGameSnapshot_(summary, matchup, lineups, conflicts),
    players: buildPlayerSnapshot_(projections, lineups),
    model_conflicts: conflicts
  };

  const json = JSON.stringify(snapshot, null, 2);
  const filename = 'nhl_model_snapshot_' + String(slateDate) + '.json';
  const folderId = PropertiesService.getScriptProperties()
    .getProperty('NHL_INTELLIGENCE_FOLDER_ID');
  const file = folderId
    ? DriveApp.getFolderById(folderId).createFile(filename, json, MimeType.PLAIN_TEXT)
    : DriveApp.createFile(filename, json, MimeType.PLAIN_TEXT);

  logExportSafe_('Intelligence Snapshot', conflicts.some(c => c.severity === 'CRITICAL') ? 'WARNING' : 'OK',
    snapshot.games.length + ' games, ' + snapshot.players.length + ' players, ' +
    conflicts.length + ' conflicts; file=' + file.getId());

  Logger.log('NHL Intelligence snapshot: ' + file.getUrl());
  return json;
}

function sheetName_(key, fallback) {
  return (typeof SHEETS !== 'undefined' && SHEETS[key]) ? SHEETS[key] : fallback;
}

function readSheetObjects_(ss, name, optional) {
  const sheet = ss.getSheetByName(name);
  if (!sheet) {
    if (optional) return [];
    throw new Error('Required Intelligence source sheet missing: ' + name);
  }
  const values = sheet.getDataRange().getValues();
  if (!values.length) return [];
  const headers = values[0].map(h => String(h || '').trim());
  return values.slice(1).filter(row => row.some(v => v !== '' && v !== null))
    .map(row => {
      const obj = {};
      headers.forEach((h, i) => { if (h) obj[h] = jsonValue_(row[i]); });
      return obj;
    });
}

function jsonValue_(v) {
  if (v instanceof Date) return v.toISOString();
  if (v === undefined) return null;
  return v;
}

function first_(obj, names, fallback) {
  for (let i = 0; i < names.length; i++) {
    const v = obj[names[i]];
    if (v !== undefined && v !== null && v !== '') return v;
  }
  return fallback === undefined ? null : fallback;
}

function buildPlayerSnapshot_(projections, lineups) {
  const lineupByKey = {};
  lineups.forEach(r => {
    const id = String(first_(r, ['NST_PlayerID'], '') || '');
    const key = id || (String(first_(r, ['Player_Name'], '')).toLowerCase() + '|' + first_(r, ['Team'], ''));
    lineupByKey[key] = r;
  });

  return projections.map(p => {
    const id = String(first_(p, ['NST_PlayerID'], '') || '');
    const key = id || (String(first_(p, ['Player_Name', 'Player'], '')).toLowerCase() + '|' + first_(p, ['Team'], ''));
    const l = lineupByKey[key] || {};
    return {
      nst_player_id: id || null,
      player: first_(p, ['Player_Name', 'Player']),
      team: first_(p, ['Team']),
      opponent: first_(p, ['Opponent']),
      home_away: first_(p, ['Home_Away']),
      line: first_(p, ['Line'], first_(l, ['Line'])),
      pp_unit: first_(p, ['PP_Unit'], first_(l, ['PP_Unit'])),
      pk_unit: first_(p, ['PK_Unit'], first_(l, ['PK_Unit'])),
      match_confidence: first_(l, ['Match_Confidence']),
      projections: {
        fs: statWindow_(p, 'FS'),
        l20: statWindow_(p, 'L20'),
        l10: statWindow_(p, 'L10')
      }
    };
  });
}

function statWindow_(r, w) {
  return {
    sog: first_(r, [w + '_Proj_SOG']),
    goals: first_(r, [w + '_Proj_G']),
    assists: first_(r, [w + '_Proj_A']),
    pim: first_(r, [w + '_Proj_PIM']),
    blocks: first_(r, [w + '_Proj_BLK'])
  };
}

function buildGameSnapshot_(summary, matchup, lineups, conflicts) {
  const teamRows = summary.length ? summary : matchup;
  const byTeam = {};
  teamRows.forEach(r => {
    const team = String(first_(r, ['Team'], '') || '').trim();
    if (team) byTeam[team] = r;
  });

  const seen = {};
  const games = [];
  Object.keys(byTeam).forEach(team => {
    const r = byTeam[team];
    const opp = String(first_(r, ['Opponent'], '') || '').trim();
    if (!opp || !byTeam[opp]) return;
    const pair = [team, opp].sort().join('-');
    if (seen[pair]) return;
    seen[pair] = true;

    const home = String(first_(r, ['Home_Away'], '')).toUpperCase() === 'H' ? team :
                 String(first_(byTeam[opp], ['Home_Away'], '')).toUpperCase() === 'H' ? opp : null;
    const away = home === team ? opp : home === opp ? team : team;
    const homeTeam = home || opp;
    const awayTeam = away || team;
    const h = byTeam[homeTeam] || {};
    const a = byTeam[awayTeam] || {};
    const gameId = awayTeam + '@' + homeTeam;

    games.push({
      game_id: gameId,
      puck_drop: first_(h, ['Puck_Drop', 'Game_Time', 'Start_Time', 'Date']),
      away: awayTeam,
      home: homeTeam,
      model: {
        away_goals: first_(a, ['Proj_G', 'Projected_Goals', 'L20_Team_G', 'FS_Team_G']),
        home_goals: first_(h, ['Proj_G', 'Projected_Goals', 'L20_Team_G', 'FS_Team_G']),
        total: sumNullable_(
          first_(a, ['Proj_G', 'Projected_Goals', 'L20_Team_G', 'FS_Team_G']),
          first_(h, ['Proj_G', 'Projected_Goals', 'L20_Team_G', 'FS_Team_G'])
        )
      },
      goalies: {
        away: goalieForTeam_(awayTeam, matchup, lineups),
        home: goalieForTeam_(homeTeam, matchup, lineups)
      },
      lineup_status: teamLineupStatus_(awayTeam, homeTeam, lineups),
      special_teams_status: specialTeamsStatus_(awayTeam, homeTeam, lineups),
      conflicts: conflicts.filter(c => c.game_id === gameId || c.teams.indexOf(awayTeam) >= 0 || c.teams.indexOf(homeTeam) >= 0)
    });
  });
  return games;
}

function goalieForTeam_(team, matchup, lineups) {
  const own = lineups.filter(r => String(first_(r, ['Team'], '')) === team);
  const flagged = own.filter(r => truthyFlag_(first_(r, ['Starting_Goalie_Flag'], '')));
  const oppRow = matchup.find(r => String(first_(r, ['Opponent'], '')) === team);
  return {
    model_name: flagged.length === 1 ? first_(flagged[0], ['Player_Name']) :
                first_(oppRow || {}, ['Opp_Starting_Goalie']),
    status: flagged.length === 1 ? 'PROJECTED' : flagged.length > 1 ? 'UNKNOWN' : 'UNKNOWN',
    candidates_flagged: flagged.map(r => first_(r, ['Player_Name'])),
    model_hdsave_pct: first_(oppRow || {}, ['Opp_Goalie_HDSVpct', 'Opp_HDSV%', 'Opp_Goalie_HDSV'])
  };
}

function teamLineupStatus_(away, home, lineups) {
  const rows = lineups.filter(r => [away, home].indexOf(String(first_(r, ['Team'], ''))) >= 0);
  const unresolved = rows.filter(r => !first_(r, ['NST_PlayerID'])).length;
  return unresolved ? 'UNRESOLVED' : 'CURRENT';
}

function specialTeamsStatus_(away, home, lineups) {
  const rows = lineups.filter(r => [away, home].indexOf(String(first_(r, ['Team'], ''))) >= 0);
  if (!rows.length) return 'UNRESOLVED';
  const hasPP = rows.some(r => first_(r, ['PP_Unit']) !== null);
  const hasPK = rows.some(r => first_(r, ['PK_Unit']) !== null);
  return hasPP && hasPK ? 'CURRENT' : 'UNRESOLVED';
}

function buildModelConflicts_(lineups, matchup, projections, summary, review) {
  const out = [];
  const add = (type, severity, message, teams, player) => out.push({
    conflict_id: type + '-' + (out.length + 1),
    type: type,
    severity: severity,
    message: message,
    teams: teams || [],
    player: player || null,
    reprojection_required: severity === 'CRITICAL'
  });

  lineups.forEach(r => {
    const name = first_(r, ['Player_Name']);
    const team = String(first_(r, ['Team'], '') || '');
    if (name && !first_(r, ['NST_PlayerID'])) {
      add('MISSING_PLAYER_ID', 'HIGH', name + ' has no NST_PlayerID', [team], name);
    }
  });

  const ids = {};
  lineups.forEach(r => {
    const id = String(first_(r, ['NST_PlayerID'], '') || '');
    if (!id) return;
    const sig = String(first_(r, ['Player_Name'], '')) + '|' + String(first_(r, ['Team'], ''));
    if (ids[id] && ids[id] !== sig) {
      add('PLAYER_ID_COLLISION', 'CRITICAL', 'NST_PlayerID ' + id + ' maps to both ' + ids[id] + ' and ' + sig,
        [ids[id].split('|')[1], String(first_(r, ['Team'], ''))], first_(r, ['Player_Name']));
    } else ids[id] = sig;
  });

  const teams = {};
  lineups.forEach(r => { const t = String(first_(r, ['Team'], '') || ''); if (t) teams[t] = true; });
  Object.keys(teams).forEach(team => {
    const gs = lineups.filter(r => String(first_(r, ['Team'], '')) === team && truthyFlag_(first_(r, ['Starting_Goalie_Flag'], '')));
    if (gs.length > 1) add('MULTIPLE_STARTING_GOALIES', 'HIGH',
      team + ' has ' + gs.length + ' rows flagged as starting goalie', [team]);
  });

  review.forEach(r => {
    const status = String(first_(r, ['Status'], '') || '').toLowerCase();
    if (status && status !== 'resolved') add('PLAYER_MATCH_REVIEW', 'HIGH',
      'Unresolved player match: ' + first_(r, ['LWL_Name'], '(unknown)'), [String(first_(r, ['LWL_Team'], '') || '')],
      first_(r, ['LWL_Name']));
  });

  if (!projections.length) add('PROJECTIONS_EMPTY', 'CRITICAL', 'Projections sheet contains no player rows', []);
  if (!summary.length) add('GAME_SUMMARY_EMPTY', 'CRITICAL', 'Game_Summary contains no team rows', []);
  if (!matchup.length) add('MATCHUP_EMPTY', 'CRITICAL', 'Matchup contains no team rows', []);
  return out;
}

function buildPipelineStatus_(runLog, now) {
  const specs = {
    dfo: ['Daily Faceoff', 'DFO', 'Lineups'],
    nst_full_season: ['FS Bulk', 'NST', 'Skater FS'],
    rolling_l20_l10: ['Rolling', 'L20', 'L10'],
    player_matching: ['Player Matching', 'Resolve', 'Manual Resolutions'],
    goalie_data: ['Goalie'],
    matchup: ['Matchup Build', 'Matchup'],
    projections: ['Projections', 'Game Summary']
  };
  const out = {};
  Object.keys(specs).forEach(k => { out[k] = latestLogStatus_(runLog, specs[k], now); });
  return out;
}

function latestLogStatus_(rows, aliases, now) {
  const matches = rows.filter(r => {
    const step = String(first_(r, ['Step'], '') || '').toLowerCase();
    return aliases.some(a => step.indexOf(a.toLowerCase()) >= 0);
  });
  if (!matches.length) return {status:'UNRESOLVED', updated_at:null, detail:'No matching Run_Log entry'};
  const r = matches[matches.length - 1];
  const raw = String(first_(r, ['Status'], 'UNRESOLVED') || '').toUpperCase();
  const status = raw === 'OK' || raw === 'COMPLETED' ? 'OK' :
                 raw === 'WARNING' ? 'WARNING' : raw === 'ERROR' ? 'ERROR' : 'UNRESOLVED';
  return {status:status, updated_at:first_(r, ['Timestamp']), detail:first_(r, ['Details'], '')};
}

function truthyFlag_(v) {
  const s = String(v || '').trim().toUpperCase();
  return s === 'TRUE' || s === 'YES' || s === 'Y' || s === '1' || s === 'STARTER' || s === 'STARTING';
}

function sumNullable_(a, b) {
  const x = Number(a), y = Number(b);
  return isFinite(x) && isFinite(y) ? x + y : null;
}

function logExportSafe_(step, status, details) {
  if (typeof logRun_ === 'function') {
    try { logRun_(step, status, details, 0); } catch (e) { Logger.log(step + ': ' + details); }
  } else Logger.log(step + ' [' + status + '] ' + details);
}
