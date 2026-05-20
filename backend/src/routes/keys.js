const { Router } = require('express');
const validate = require('../middleware/validate');

function keyRoutes(keyController, authMw) {
  const router = Router();

  router.use(authMw);

  router.post('/', validate.publishKey, keyController.publish);
  router.get('/', keyController.listKeys);
  router.get('/:userId', keyController.getKey);
  // Audit trail — clients reconcile their pinned key against this to detect
  // server-side substitution. Public to authenticated users so the recipient
  // of a forwarded message can verify the sender's key has not been swapped.
  router.get('/:userId/history/:keyType', keyController.getHistory);

  return router;
}

module.exports = keyRoutes;
