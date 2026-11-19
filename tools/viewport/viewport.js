import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import idleClips from "./idle-clips.json";

function sampleIdleClip(clip, part, seconds, pose, nextPose) {
    const keys = clip.parts[part];
    const frame = (seconds % clip.duration) / clip.duration * (keys.length - 1);
    const index = Math.floor(frame);
    pose.fromArray(keys[index]).normalize();
    nextPose.fromArray(keys[Math.min(index + 1, keys.length - 1)]).normalize();
    pose.slerp(nextPose, frame - index);
}

const SIZE = 64;
const ALPHA = 48;
const faces = ["right", "front", "left", "back", "top", "bottom"];
const shade = [0.91, 1, 0.93, 0.96, 1, 0.82];

function faceBoxes([u, v], w, h, d) {
    return [[u, v + d, d, h], [u + d, v + d, w, h],
        [u + d + w, v + d, d, h], [u + 2 * d + w, v + d, w, h],
        [u + d, v, w, d], [u + d + w, v, w, d]];
}

function cuboid(center, [w, h, d], origin, blowup, material) {
    const [cx, cy, cz] = center;
    const a = w / 2 + blowup, b = h / 2 + blowup, c = d / 2 + blowup;
    const boxes = faceBoxes(origin, w, h, d);
    const corners = [
        [[a,b,c],[a,b,-c],[a,-b,-c],[a,-b,c]],
        [[-a,b,c],[a,b,c],[a,-b,c],[-a,-b,c]],
        [[-a,b,-c],[-a,b,c],[-a,-b,c],[-a,-b,-c]],
        [[a,b,-c],[-a,b,-c],[-a,-b,-c],[a,-b,-c]],
        [[-a,b,c],[a,b,c],[a,b,-c],[-a,b,-c]],
        [[-a,-b,-c],[a,-b,-c],[a,-b,c],[-a,-b,c]],
    ];
    const points = [], uv = [], colors = [], indices = [];
    for (let f = 0; f < faces.length; f++) {
        const [x, y, width, height] = boxes[f];
        const u0 = x / SIZE, u1 = (x + width) / SIZE;
        const v0 = 1 - y / SIZE, v1 = 1 - (y + height) / SIZE;
        uv.push(u0,v0,u1,v0,u1,v1,u0,v1);
        for (const [px, py, pz] of corners[f]) {
            points.push(px + cx, py + cy, pz + cz);
            colors.push(shade[f], shade[f], shade[f]);
        }
        const quad = f < 4 ? [0,2,1,0,3,2] : [0,1,2,0,2,3];
        indices.push(...quad.map(i => i + f * 4));
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
    geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
    geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    geometry.setIndex(indices);
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData.boxes = boxes;
    mesh.userData.layer = blowup ? "outer" : "base";
    mesh.renderOrder = blowup ? 1 : 0;
    return mesh;
}

function buildPlayer(group, slim, base, outer) {
    for (const mesh of [...group.children]) {
        group.remove(mesh);
        mesh.geometry.dispose();
    }
    const arm = slim ? 3 : 4;
    const parts = [
        ["Head",[0,28,0],[8,8,8],[0,0],[32,0],.50],
        ["Torso",[0,18,0],[8,12,4],[16,16],[16,32],.25],
        ["Right arm",[-4-arm/2,18,0],[arm,12,4],[40,16],[40,32],.25],
        ["Left arm",[4+arm/2,18,0],[arm,12,4],[32,48],[48,48],.25],
        ["Right leg",[-2,6,0],[4,12,4],[0,16],[0,32],.25],
        ["Left leg",[2,6,0],[4,12,4],[16,48],[0,48],.25],
    ];
    for (const [part, center, dimensions, baseUv, overlayUv, expansion] of parts) {
        const baseMesh = cuboid(center, dimensions, baseUv, 0, base);
        const outerMesh = cuboid(center, dimensions, overlayUv, expansion, outer);
        baseMesh.userData.part = outerMesh.userData.part = part;
        if (part === "Head" || part.endsWith("arm")) {
            const pivot = new THREE.Vector3(center[0], part === "Head" ? 24 : 23, center[2]);
            baseMesh.userData.idlePivot = outerMesh.userData.idlePivot = pivot;
        }
        group.add(baseMesh, outerMesh);
    }
    group.updateMatrixWorld(true);
}

function createTexture() {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = SIZE;
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.minFilter = texture.magFilter = THREE.NearestFilter;
    texture.generateMipmaps = false;
    return texture;
}

function updateTexture(texture, encoded) {
    const pixels = Uint8ClampedArray.from(atob(encoded), c => c.charCodeAt(0));
    texture.image.getContext("2d").putImageData(new ImageData(pixels, SIZE, SIZE), 0, 0);
    texture.needsUpdate = true;
    return pixels;
}

function start(host) {
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false });
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.autoClear = false;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    const canvas = renderer.domElement;
    const viewport = document.getElementById("viewport");
    viewport.append(canvas);
    const svg = "http://www.w3.org/2000/svg";
    const outline = document.createElementNS(svg, "svg");
    outline.setAttribute("class", "pixel-outline");
    outline.setAttribute("aria-hidden", "true");
    outline.style.visibility = "hidden";
    const border = document.createElementNS(svg, "polygon");
    border.setAttribute("fill", "#a66ce1");
    border.setAttribute("fill-opacity", ".27");
    border.setAttribute("stroke", "#36234f");
    border.setAttribute("stroke-width", "4");
    border.setAttribute("stroke-linejoin", "round");
    const rim = border.cloneNode();
    rim.setAttribute("fill", "none");
    rim.setAttribute("stroke", "white");
    rim.setAttribute("stroke-width", "2");
    outline.append(border, rim);
    viewport.append(outline);
    const scene = new THREE.Scene();
    const player = new THREE.Group();
    scene.add(player);
    const camera = new THREE.OrthographicCamera(-20, 20, 20, -20, 1, 300);
    const controls = new OrbitControls(camera, canvas);
    controls.target.set(0, 16, 0);
    controls.enablePan = false;
    controls.enableDamping = false;
    controls.minZoom = .65;
    controls.maxZoom = 3;
    controls.mouseButtons = {LEFT: null, MIDDLE: THREE.MOUSE.ROTATE, RIGHT: null};
    const original = createTexture(), styled = createTexture();
    const base = new THREE.MeshBasicMaterial({map: styled, vertexColors: true, alphaTest: .001});
    const outer = new THREE.MeshBasicMaterial({
        map: styled, vertexColors: true, alphaTest: .001, transparent: true,
    });
    const aspect = () => canvas.clientWidth / Math.max(1, canvas.clientHeight);
    let packet, sourcePixels, styledPixels, geometrySlim, lastYaw, scheduled = false, ready = false;
    let lastPacket = "", lastWidth = 0, lastHeight = 0;
    let idleTimer = null;
    const idlePose = new THREE.Quaternion();
    const chatPose = new THREE.Quaternion();
    const nextPose = new THREE.Quaternion();

    function schedule() {
        if (!scheduled) {
            scheduled = true;
            requestAnimationFrame(draw);
        }
    }
    function pose(yaw) {
        const theta = THREE.MathUtils.degToRad(yaw);
        const pitch = THREE.MathUtils.degToRad(11);
        camera.position.set(-70 * Math.cos(pitch) * Math.sin(theta),
            70 * Math.sin(pitch), 70 * Math.cos(pitch) * Math.cos(theta)).add(controls.target);
        camera.lookAt(controls.target);
        controls.update();
    }
    function sceneStateChanged() {
        controls.enabled = host.editable;
        if (lastYaw !== host.yaw) {
            lastYaw = host.yaw;
            pose(lastYaw);
        }
        schedule();
    }
    function updateVisibility() {
        endStroke();
        clearHover();
        const hidden = new Set(host.hiddenParts.split(","));
        for (const mesh of player.children) {
            mesh.visible = !host.editable || (!hidden.has(mesh.userData.part)
                && (host.layer === "visible" || host.layer === mesh.userData.layer));
        }
        schedule();
    }
    function frame(texture, x, w, h) {
        if (w < 1) return;
        base.map = outer.map = texture;
        renderer.setScissor(x, 0, w, h);
        renderer.render(scene, camera);
    }
    function draw(time) {
        scheduled = false;
        const w = canvas.clientWidth, h = canvas.clientHeight;
        if (!w || !h || !packet) return;
        if (w !== lastWidth || h !== lastHeight) {
            lastWidth = w; lastHeight = h;
            const halfHeight = Math.max(19.6, 9 / aspect());
            camera.top = halfHeight;
            camera.bottom = -halfHeight;
            camera.left = -halfHeight * aspect();
            camera.right = halfHeight * aspect();
            camera.updateProjectionMatrix();
            renderer.setSize(w, h, false);
        }
        const animate = host.idleAnimation && !document.hidden;
        const seconds = time / 1000;
        const chatTime = seconds % 16 - 9;
        const chatWeight = THREE.MathUtils.smoothstep(chatTime, 0, .45)
            * (1 - THREE.MathUtils.smoothstep(chatTime, 2.45, 2.9));
        for (const mesh of player.children) {
            const part = mesh.userData.part;
            const pivot = mesh.userData.idlePivot;
            if (!pivot) continue;
            mesh.quaternion.identity();
            if (animate) {
                sampleIdleClip(idleClips["relaxed-idle"], part, seconds, idlePose, nextPose);
                if (chatWeight > 0) {
                    sampleIdleClip(idleClips.chatting, part, chatTime, chatPose, nextPose);
                    idlePose.slerp(chatPose, chatWeight);
                }
                mesh.quaternion.slerp(idlePose, part === "Head" ? .85 : .65);
            }
            // Keep the joint fixed while rotating the base and outer layers together.
            mesh.position.copy(pivot).applyQuaternion(mesh.quaternion).negate().add(pivot);
        }
        renderer.setScissorTest(false);
        renderer.clear(true, true, true);
        renderer.setScissorTest(true);
        const cut = Math.round(w * host.wipe);
        if (host.mode === "Compare") {
            frame(original, 0, cut, h);
            frame(styled, cut, w - cut, h);
        } else {
            frame(host.mode === "Original" ? original : styled, 0, w, h);
        }
        if (hoverPoint) reportHover(pick(hoverPoint.x, hoverPoint.y));
        if (!ready) {
            ready = true;
            host.surfaceReady(true);
        }
        if (animate && idleTimer === null) {
            idleTimer = setTimeout(() => {
                idleTimer = null;
                if (host.idleAnimation && !document.hidden) schedule();
            }, 32);
        }
    }
    function updatePacket() {
        if (lastPacket === host.packet) return;
        lastPacket = host.packet;
        if (!lastPacket) {
            clearHover();
            packet = undefined;
            renderer.setScissorTest(false);
            renderer.clear();
            return;
        }
        const next = JSON.parse(lastPacket);
        if (packet?.token !== next.token) clearHover();
        packet = next;
        if (geometrySlim !== packet.slim) {
            geometrySlim = packet.slim;
            buildPlayer(player, packet.slim, base, outer);
            updateVisibility();
        }
        sourcePixels = updateTexture(original, packet.original);
        styledPixels = updateTexture(styled, packet.styled);
        schedule();
    }

    // Adapted from Lynn's Blockygotchi 3D controls and coordinate helpers.
    // Corrections target visible source texels, so a transparent hat pixel
    // can't take a hit intended for the hair beneath it.
    const pointer = new THREE.Vector2(), raycaster = new THREE.Raycaster();
    function pick(clientX, clientY) {
        if (!packet) return null;
        const rect = canvas.getBoundingClientRect();
        if (!rect.width || !rect.height || clientX < rect.left || clientX >= rect.right
                || clientY < rect.top || clientY >= rect.bottom) return null;
        pointer.set((clientX - rect.left) / rect.width * 2 - 1,
                    1 - (clientY - rect.top) / rect.height * 2);
        const shownPixels = host.mode === "Original" ||
            (host.mode === "Compare" && clientX - rect.left < Math.round(rect.width * host.wipe))
            ? sourcePixels : styledPixels;
        camera.updateMatrixWorld();
        raycaster.setFromCamera(pointer, camera);
        for (const hit of raycaster.intersectObjects(player.children, false)) {
            if (!hit.object.visible || !hit.uv || hit.faceIndex == null) continue;
            const face = Math.floor(hit.faceIndex / 2);
            const [u, v, w, h] = hit.object.userData.boxes[face];
            // Clamp to the intersected face, not the neighboring atlas tile.
            const x = Math.min(u + w - 1, Math.max(u, Math.floor(hit.uv.x * SIZE)));
            const y = Math.min(v + h - 1, Math.max(v, Math.floor((1 - hit.uv.y) * SIZE)));
            const i = (y * SIZE + x) * 4 + 3;
            if (sourcePixels[i] >= ALPHA && shownPixels[i] >= ALPHA)
                return {x, y, face, mesh: hit.object};
        }
        return null;
    }
    function outlinePixel(cell) {
        outline.style.visibility = cell ? "visible" : "hidden";
        if (!cell) return;
        const {x, y, face, mesh} = cell;
        const [u, v, w, h] = mesh.userData.boxes[face];
        const positions = mesh.geometry.attributes.position;
        const topLeft = new THREE.Vector3().fromBufferAttribute(positions, face * 4);
        const across = new THREE.Vector3().fromBufferAttribute(positions, face * 4 + 1).sub(topLeft);
        const down = new THREE.Vector3().fromBufferAttribute(positions, face * 4 + 3).sub(topLeft);
        const corners = [[x, y], [x + 1, y], [x + 1, y + 1], [x, y + 1]];
        const points = corners.map(([px, py]) => {
            const vertex = topLeft.clone().addScaledVector(across, (px - u) / w)
                .addScaledVector(down, (py - v) / h);
            const screen = mesh.localToWorld(vertex).project(camera);
            return `${(1 + screen.x) * canvas.clientWidth / 2},${(1 - screen.y) * canvas.clientHeight / 2}`;
        }).join(" ");
        border.setAttribute("points", points);
        rim.setAttribute("points", points);
    }

    let stroke = null, hover = "", hoverPoint = null, orbitPoint = null;
    function reportHover(cell) {
        outlinePixel(cell);
        const key = cell ? `${cell.x}:${cell.y}` : "";
        if (key !== hover) {
            hover = key;
            host.highlight(packet?.token || "", cell?.x ?? -1, cell?.y ?? -1);
        }
    }
    function clearHover() {
        hoverPoint = null;
        reportHover(null);
    }
    function setHover(x, y) {
        hoverPoint = {x, y};
        reportHover(pick(x, y));
    }
    function setZoom(zoom) {
        camera.zoom = THREE.MathUtils.clamp(zoom, controls.minZoom, controls.maxZoom);
        camera.updateProjectionMatrix();
        host.reportZoom(camera.zoom);
        schedule();
    }
    function queueCells(x, y) {
        if (packet?.token !== stroke.token) return;
        const previous = stroke.previous;
        const steps = Math.min(128, Math.max(1, Math.ceil(Math.hypot(x - previous.x, y - previous.y) / 2)));
        const cells = [];
        for (let i = 1; i <= steps; i++) {
            const hit = pick(previous.x + (x - previous.x) * i / steps,
                             previous.y + (y - previous.y) * i / steps);
            if (!hit) continue;
            const key = hit.y * SIZE + hit.x;
            if (stroke.seen.has(key)) continue;
            stroke.seen.add(key);
            cells.push(key);
        }
        if (cells.length) host.paint(stroke.token, cells, stroke.restore);
        stroke.previous = {x, y};
    }
    function endStroke() {
        if (stroke) {
            host.finish(stroke.token);
            stroke = null;
        }
    }
    // A texel is reviewable only if its center projects on screen and the
    // existing transparent-aware ray picker hits that very texel first.
    function reviewVisible(approve) {
        endStroke();
        if (!packet || !host.canPaint) return;
        const rect = canvas.getBoundingClientRect(), cells = new Set();
        camera.updateMatrixWorld();
        player.updateMatrixWorld(true);
        for (const mesh of player.children) {
            if (!mesh.visible) continue;
            const positions = mesh.geometry.attributes.position;
            for (let face = 0; face < 6; face++) {
                const [u, v, w, h] = mesh.userData.boxes[face];
                const origin = new THREE.Vector3().fromBufferAttribute(positions, face * 4);
                const across = new THREE.Vector3().fromBufferAttribute(positions, face * 4 + 1).sub(origin);
                const down = new THREE.Vector3().fromBufferAttribute(positions, face * 4 + 3).sub(origin);
                for (let y = v; y < v + h; y++) for (let x = u; x < u + w; x++) {
                    if (sourcePixels[(y * SIZE + x) * 4 + 3] < ALPHA) continue;
                    const p = origin.clone().addScaledVector(across, (x + .5 - u) / w)
                        .addScaledVector(down, (y + .5 - v) / h);
                    const screen = mesh.localToWorld(p).project(camera);
                    if (screen.z < -1 || screen.z > 1) continue;
                    const hit = pick(rect.left + (screen.x + 1) * rect.width / 2,
                                     rect.top + (1 - screen.y) * rect.height / 2);
                    if (hit && hit.mesh === mesh && hit.face === face && hit.x === x && hit.y === y)
                        cells.add(y * SIZE + x);
                }
            }
        }
        host.review(packet.token, [...cells], approve);
    }
    // Qt owns the editor gestures; forward viewport-local positions instead
    // of relying on Chromium focus or native pointer capture inside QML.
    window.ddViewportInput = ([action, x, y, button]) => {
        if (!host.editable) {
            if (action === "resetView") {
                orbitPoint = null;
                pose(host.yaw);
                schedule();
                return;
            }
            if (action === "orbitStart") {
                orbitPoint = {x, y};
                return;
            }
            if (action === "finish") {
                orbitPoint = null;
                return;
            }
            if (action !== "move" || !orbitPoint) return;
        }
        // Use the same channel as paints so an immediate Undo waits for clicks
        // and stroke commits already dispatched by the desktop editor.
        if (action === "undo" || action === "redo") {
            endStroke();
            host.stepHistory(action === "undo");
            return;
        }
        if (action === "navigate") {
            endStroke();
            host.navigate(button);
            return;
        }
        if (action === "approve" || action === "unapprove") {
            reviewVisible(action === "approve");
            return;
        }
        if (!packet) return;
        if (action === "match") {
            endStroke();
            const hit = pick(x, y);
            if (hit && host.canPaint) host.matchColor(packet.token, hit.x, hit.y);
            setHover(x, y);
        } else if (action === "press" || action === "pan") {
            endStroke();
            if (button === 4) {
                orbitPoint = {x, y, pan: action === "pan"};
                clearHover();
            } else if (host.canPaint && (button === 1 || button === 2)) {
                stroke = {token: packet.token, previous: {x, y},
                          restore: button === 2, seen: new Set()};
                queueCells(x, y);
                setHover(x, y);
            }
        } else if (action === "move") {
            if (orbitPoint?.pan) {
                const units = (camera.top - camera.bottom) / (camera.zoom * Math.max(1, canvas.clientHeight));
                const shift = new THREE.Vector3(orbitPoint.x - x, y - orbitPoint.y, 0)
                    .multiplyScalar(units).applyQuaternion(camera.quaternion);
                camera.position.add(shift);
                controls.target.add(shift);
                orbitPoint = {x, y, pan: true};
                controls.update();
                schedule();
            } else if (orbitPoint) {
                const speed = 2 * Math.PI / Math.max(1, canvas.clientHeight);
                const offset = camera.position.clone().sub(controls.target);
                const spherical = new THREE.Spherical().setFromVector3(offset);
                spherical.theta -= (x - orbitPoint.x) * speed;
                spherical.phi -= (y - orbitPoint.y) * speed;
                spherical.makeSafe();
                offset.setFromSpherical(spherical);
                camera.position.copy(controls.target).add(offset);
                orbitPoint = {x, y};
                controls.update();
                schedule();
            } else {
                setHover(x, y);
                if (stroke) queueCells(x, y);
            }
        } else if (action === "wheel") {
            setZoom(camera.zoom * Math.pow(1.14, button / 120));
        } else if (action === "zoom" || action === "fit") {
            clearHover();
            if (action === "fit") {
                camera.position.sub(controls.target).add(new THREE.Vector3(0, 16, 0));
                controls.target.set(0, 16, 0);
                controls.update();
            }
            setZoom(action === "fit" ? 1 : camera.zoom * button);
        } else if (action === "leave") {
            clearHover();
        } else if (action === "finish") {
            endStroke();
            orbitPoint = null;
        }
    };
    canvas.addEventListener("webglcontextlost", () => {
        endStroke();
        host.surfaceReady(false);
    });
    window.addEventListener("blur", endStroke);
    new ResizeObserver(schedule).observe(canvas);
    controls.addEventListener("change", schedule);
    host.idleAnimationChanged.connect(schedule);
    document.addEventListener("visibilitychange", schedule);
    host.packetChanged.connect(updatePacket);
    host.layerChanged.connect(updateVisibility);
    host.hiddenPartsChanged.connect(updateVisibility);
    for (const name of ["modeChanged", "wipeChanged", "yawChanged", "editableChanged"])
        host[name].connect(sceneStateChanged);
    sceneStateChanged();
    updatePacket();
}

if (window.qt?.webChannelTransport && window.QWebChannel) {
    new window.QWebChannel(qt.webChannelTransport, channel => {
        const host = channel.objects.host;
        try { start(host); }
        catch (error) {
            console.error(error);
            host.surfaceReady(false);
        }
    });
}
