const { randomUUID } = require('crypto');

/**
 * Attaches a UUID to every request as req.id, exposes it via the
 * X-Request-Id response header, and stamps it on the child logger.
 *
 * Honours an inbound X-Request-Id only if it looks like a UUID — refusing
 * arbitrary client-supplied strings prevents log-poisoning where an
 * attacker tries to mask their actions by submitting forged correlation
 * IDs that match a legitimate user's previous traffic.
 */
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function requestId(req, res, next) {
  const inbound = req.headers['x-request-id'];
  req.id = (typeof inbound === 'string' && UUID_RE.test(inbound)) ? inbound : randomUUID();
  res.setHeader('X-Request-Id', req.id);
  next();
}

module.exports = requestId;
