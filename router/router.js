const express = require('express');
const router = express.Router();
const router_handler = require('../router_handler/router_handler.js') 

router.post('/run', router_handler.runPy)

router.get('/tableInEla', router_handler.outTable)




module.exports = router;