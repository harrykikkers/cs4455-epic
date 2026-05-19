const { Router } = require('express');
const validate = require('../middleware/validate');

function messageRoutes(messageController, authMw) {
  const router = Router();

  // All message routes require authentication
  router.use(authMw);

  router.post('/', validate.sendMessage, messageController.send);
  router.get('/inbox', validate.pagination, messageController.inbox);
  router.get('/sent', validate.pagination, messageController.sent);
  router.get('/:id', messageController.getOne);
  router.post('/:id/forward', validate.forwardMessage, messageController.forward);
  router.post('/:id/revoke', validate.revokeAccess, messageController.revoke);
  router.delete('/:id', messageController.remove);

  return router;
}

module.exports = messageRoutes;
