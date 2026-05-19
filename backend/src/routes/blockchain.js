const { Router } = require('express');
const { body } = require('express-validator');

function blockchainRoutes(blockchainController) {
  const router = Router();

  // Verification is public — the standalone verification page calls this
  router.post('/verify', [
    body('content').notEmpty().withMessage('Content to verify is required'),
  ], blockchainController.verify);

  return router;
}

module.exports = blockchainRoutes;
