const spawn = require('child_process').spawn
const formidable = require('formidable')
const path = require('path')

exports.upload = (req, res) => {
    const form = new formidable.IncomingForm()
    form.uploadDir = path.join(__dirname, 'assets', 'uploads')

    form.keepExtenSions = true
    form.parse(req, (err, fields, files) => {
        var imagePath = {
            todo: 'savePath',
            path: files.attrName.filepath.split('assets')[1],
            fileBinarName: files.attrName.filepath.split("uploads\\")[1],
            fileName: files.attrName.originalFilename
        }


        const imagePathStr = JSON.stringify(imagePath)

        const py = spawn('python', ['main.py', imagePathStr])

        /* Output the print content in the py file */
        py.stdout.on('data', function (resultSearch) {
            const data = resultSearch.toString()
            console.log(data)

        })
        res.send(imagePath)
    })
}

exports.runPy = (req, res) => {
    const form = new formidable.IncomingForm()
    form.parse(req, (err, fields, files) => {
        res.send(fields)

    })

    const body = req.body
    if (body.model && body.file) {

        const run = {
            'todo': 'run',
            'file': body.file,
            'model': body.model
        }

        const runStr = JSON.stringify(run)
        const py = spawn('python', ['main.py', runStr])

        /* Output the print content in the py file */
        py.stdout.on('data', function (resultSearch) {
            const data = JSON.parse(resultSearch.toString())
            console.log(data)
            res.send(data)
        })
    }
}


exports.returnTable = (req, res) => {
    console.log(res.body)
}

exports.returnSearch = (req, res) => {
    const body = req.body


    const search = {
        'todo': 'search',
        'idx': body.idx,
        'label': body.label
    }
    console.log(search)
    const searchJSON = JSON.stringify(search)
    const py = spawn('python', ['main.py', searchJSON])

    /* Output the print content in the py file */
    py.stdout.on('data', function (resultSearch) {
        const data = JSON.parse(resultSearch.toString())
        console.log(data)
        res.send(data)
    })
}

exports.searchLabel = (req, res) => {
    const body = req.body
    const search = {
        'todo': 'searchLabel',
        'idx': body.idx,
        'label': body.label //actually is here 'all'
    }
    console.log(search)
    const searchJSON = JSON.stringify(search)
    const py = spawn('python', ['main.py', searchJSON])

    /* Output the print content in the py file */
    py.stdout.on('data', function (resultSearch) {
        const data = resultSearch.toString()
        console.log('Add labels ' + data)
        res.send(data)
    })
}

exports.imageOriSchow = (req, res) => {
    const body = req.body


    const search = { 
        'todo': 'showOri',
        'image': body.image,
    }
    const searchJSON = JSON.stringify(search)
    const py = spawn('python', ['main.py', searchJSON])

    /* Output the print content in the py file */
    py.stdout.on('data', function (resultSearch) {
        const data = JSON.parse(resultSearch.toString())
        res.send(data)
    })

}
