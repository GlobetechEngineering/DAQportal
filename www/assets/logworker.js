onmessage = (e) => {
	handleLog(e.data).then(
		(file) => {postMessage({status:'finished',value:file})},
		(err) => {postMessage({status:'error',value:err})}
	);
}

async function handleLog(url) {
	const file_response = await fetch(url);
	const file_buffer = await file_response.arrayBuffer();
	
	postMessage({status:'downloaded',value:file_buffer.byteLength});
	
	const header_data = readHeader(file_buffer);
	const header_length = 8;
	
	const endian = header_data.littleEndian;
	
	const entry_length = 1 + 12 + 2*header_data.word_count;
	const entry_count = Math.floor((file_buffer.byteLength - header_length) / entry_length);
	
	const lines = new Array(entry_count);
	
	const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
	
	let last_id = -1;
	
	for(let i = 0; i < entry_count; i++) {
		const entry = new DataView(file_buffer, header_length + i*entry_length, entry_length);
		if(entry.getUint8(0) != 0)
			throw new Error("Invalid entry at " + i);
		
		const ts = {
			Y: entry.getUint16(1, endian),
			M: entry.getUint8(3),
			D: entry.getUint8(4),
			h: entry.getUint8(6),
			m: entry.getUint8(7),
			s: entry.getUint8(8),
			n: entry.getUint32(9, endian),
			w: days[entry.getUint8(5) - 1]
		};
		
		const date = `${ts.Y}-${ts.M.toString().padStart(2,'0')}-${ts.D.toString().padStart(2,'0')}`;
		const time = `${ts.h}:${ts.m.toString().padStart(2,'0')}:${ts.s.toString().padStart(2,'0')}.${ts.n.toString().padStart(9,'0')}`;
		const ts_str = `${ts.w},${date},${time}`;
		
		const id = entry.getUint16(13, endian);
		const vars = await getVarDefs(id);
		const vals = new Array(vars.length);
		
		for(let i = 0; i < vars.length; i++) {
			const type = vars[i][0];
			
			const addr = (type == 'BOOL') ?
				vars[i][1].split('.').map(x => parseInt(x)) : parseInt(vars[i][1]);
				
			let val;
			switch(type) {
				case 'BOOL':
					val = (entry.getUint8(13 + addr[0]) & (1 << addr[1])) ? 'TRUE' : 'FALSE';
					break;
				case 'WORD':
					val = entry.getUint16(13 + addr, endian);
					break;
				case 'DWORD':
					val = entry.getUint32(13 + addr, endian);
					break;
				case 'INT':
					val = entry.getInt16(13 + addr, endian);
					break;
				case 'DINT':
					val = entry.getInt32(13 + addr, endian);
					break;
				case 'REAL':
					val = entry.getFloat32(13 + addr, endian);
					break;
			}
			
			// String.toString returns the same string so whatever
			vals[i] = val.toString();
		}
		
		const row = ts_str + ',' + vals.join(',') + '\n';
		
		if(id != last_id) {
			lines[i] = 'Day,Date,Time,' + vars.map(def => def[2]).join(',') + '\n' + row;
			last_id = id;
		}
		else {
			lines[i] = row;
		}
	}
	
	const file = new File(lines, 'file.csv');
	
	return URL.createObjectURL(file);
}

function readHeader(buffer) {
	const header = new Uint8Array(buffer, 0, 8);
	
	if(
		   header[0] != 0x61
		|| header[1] != 0x0b
		|| header[2] != 0xe7
		|| header[3] != 0xec
	)
		throw new Error("Invalid magic number");
		
	let littleEndian = null;
	
	if(
		   header[4] == 0x4e
		&& header[5] == 0x50
	)
		littleEndian = true;
	else if(
		   header[4] == 0x50
		&& header[5] == 0x4e
	)
		littleEndian = false;
	else
		throw new Error("Invalid endian flag");
	
	let version = header[6];
	if(version != 1)
		throw new Error("Unsupported version " + version);
	
	const word_count = header[7];
	
	return {
		littleEndian: littleEndian,
		word_count: word_count
	};
}

const varDefs = {};

async function getVarDefs(id) {
	// check it
	if(id in varDefs)
		return varDefs[id];
	
	// fetch it
	const response = await fetch(`/files/variables/dataconfig${id}.txt`);
	if( ! response.ok )
		throw new Error(`No configuration for ${id}`);
	const config = await response.text(); // ? Might need blob() -> text()
	
	// parse it
	const varDef = [];
	
	const lines = config.split(/\r?\n|\r/g);
	
	for(let i = 0; i < lines.length; i++) {
		if(lines[i].length == 0)
			break;
		
		varDef.push(lines[i].split(','));
	}
	
	// cache it
	varDefs[id] = varDef;
	
	return varDef;
}
