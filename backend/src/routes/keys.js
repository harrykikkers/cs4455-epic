const { Router } = require('express');
const validate = require('../middleware/validate');

function keyRoutes(keyController, authMw) {
  const router = Router();

  router.use(authMw);

  router.post('/', validate.publishKey, keyController.publish);
  router.get('/', keyController.listKeys);
  router.get('/:userId', keyController.getKey);

  return router;
}

module.exports = keyRoutes;
