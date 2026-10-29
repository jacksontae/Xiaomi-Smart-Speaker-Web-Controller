// Members (admin): list, add, edit role/name, disable, reset password, delete.
import { h, icon, fmtRel, openSheet, segmented, switchRow, inlineConfirm, field, busy, initial } from '../ui.js';
import { ROLE_TH, thaiError } from '../api.js';

const ROLE_OPTS = [{ value: 'viewer', label: ROLE_TH.viewer }, { value: 'operator', label: ROLE_TH.operator }, { value: 'admin', label: ROLE_TH.admin }];
const ROLE_DESC = {
  viewer: 'ดูสิ่งที่กำลังเล่น เพลย์ลิสต์ และวลีด่วนได้อย่างเดียว',
  operator: 'ประกาศ เล่นเพลง ปรับเสียง และแก้ไขเพลย์ลิสต์กับวลีด่วนได้',
  admin: 'ทำได้ทุกอย่าง รวมถึงจัดการสมาชิก การตั้งค่า และดูประวัติการใช้งาน',
};
const LAST_ADMIN = 'ต้องมีผู้ดูแลที่ใช้งานได้อย่างน้อย 1 คน และแก้บทบาท ปิด หรือลบบัญชีของตัวเองไม่ได้';

function roleField(value, onChange) {
  const desc = h('p', { class: 'hint', style: { marginTop: '8px', fontSize: 'var(--fs-sm)', color: 'var(--ink-2)' } }, ROLE_DESC[value]);
  const seg = segmented({ options: ROLE_OPTS, value, label: 'บทบาท', onChange: (v) => { desc.textContent = ROLE_DESC[v]; onChange(v); } });
  return { el: h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'บทบาท'), seg, desc), seg };
}

export default function membersView(ctx) {
  let users = [];
  const list = h('ul', { class: 'list' });
  const panel = h('section', { class: 'panel glass', 'aria-label': 'รายชื่อสมาชิก' }, h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' }));
  const addBtn = h('button', { class: 'btn primary', type: 'button', onclick: () => addSheet() }, icon('plus', 'sm'), 'เพิ่มสมาชิก');
  const node = h('div', {}, h('div', { class: 'page-head' }, h('h1', {}, 'สมาชิก'), h('div', { class: 'actions' }, addBtn)), panel);

  async function load() {
    try { users = await ctx.api('/users'); } catch (e) { ctx.fail(e); panel.replaceChildren(); return; }
    draw();
  }
  function draw() {
    const order = { admin: 0, operator: 1, viewer: 2 };
    users.sort((a, b) => (a.disabled - b.disabled) || (order[a.role] - order[b.role]) || a.display_name.localeCompare(b.display_name, 'th'));
    list.replaceChildren(...users.map((u) => h('li', {}, h('button', { type: 'button', class: 'row', onclick: () => editSheet(u), 'aria-label': `แก้ไข ${u.display_name}, ${ROLE_TH[u.role]}${u.disabled ? ', ปิดใช้งาน' : ''}` },
      h('span', { class: 'avatar', style: { width: '44px', height: '44px', opacity: u.disabled ? 0.45 : 1 } }, initial(u.display_name)),
      h('span', { class: 'body' }, h('span', { class: 'title' }, u.display_name, u.id === ctx.user.id ? h('span', { class: 'muted', style: { fontWeight: 500 } }, ' (คุณ)') : null),
        h('span', { class: 'sub' }, h('span', {}, `@${u.username}`), h('span', {}, u.last_login_at ? `เข้าใช้ ${fmtRel(u.last_login_at)}` : 'ยังไม่เคยเข้าใช้'))),
      h('span', { class: 'trail' }, u.disabled ? h('span', { class: 'badge off' }, 'ปิดใช้งาน') : h('span', { class: `badge ${u.role === 'admin' ? 'admin' : ''}` }, ROLE_TH[u.role]), icon('chev', 'sm'))))));
    panel.replaceChildren(list);
  }

  function addSheet() {
    openSheet({
      title: 'เพิ่มสมาชิก',
      build(body, sheet) {
        let role = 'operator';
        const name = h('input', { class: 'input', required: true, autocomplete: 'off', placeholder: 'เช่น สมชาย ใจดี' });
        const user = h('input', { class: 'input', required: true, autocomplete: 'off', autocapitalize: 'none', spellcheck: false, placeholder: 'เช่น somchai' });
        const pw = h('input', { class: 'input', type: 'password', required: true, minLength: 8, autocomplete: 'new-password' });
        user.addEventListener('input', () => { user.value = user.value.toLowerCase(); });
        const err = h('p', { class: 'form-error', role: 'alert' });
        const btn = h('button', { class: 'btn primary wide', type: 'submit' }, 'เพิ่มสมาชิก');
        const rf = roleField(role, (v) => { role = v; });
        body.append(h('form', {
          onsubmit: async (e) => {
            e.preventDefault();
            err.textContent = '';
            if (!/^[a-z0-9._-]{3,32}$/.test(user.value)) { err.textContent = 'ชื่อผู้ใช้ใช้ได้เฉพาะ a–z ตัวเลข จุด ขีด ยาว 3–32 ตัว'; return user.focus(); }
            if (pw.value.length < 8) { err.textContent = 'รหัสผ่านต้องยาวอย่างน้อย 8 ตัวอักษร'; return pw.focus(); }
            await busy(btn, async () => {
              try {
                const u = await ctx.api('/users', { body: { username: user.value, display_name: name.value.trim(), password: pw.value, role } });
                users.push(u); draw(); sheet.close();
                ctx.toast(`เพิ่ม ${u.display_name} แล้ว แจ้งชื่อผู้ใช้และรหัสผ่านให้เจ้าตัว`, 'ok', 5000);
              } catch (e2) { err.textContent = thaiError(e2, ctx.user, { 409: 'ชื่อผู้ใช้นี้มีคนใช้แล้ว ลองชื่ออื่น' }); }
            });
          },
        }, field('ชื่อที่แสดง', name), field('ชื่อผู้ใช้', user, 'ตัวพิมพ์เล็ก a–z ตัวเลข จุด หรือขีด 3–32 ตัว ใช้ตอนเข้าสู่ระบบ'),
        field('รหัสผ่านเริ่มต้น', pw, 'อย่างน้อย 8 ตัวอักษร เจ้าตัวเปลี่ยนเองได้ภายหลัง'), rf.el, err, btn));
      },
    });
  }

  function editSheet(u) {
    const self = u.id === ctx.user.id;
    openSheet({
      title: u.display_name,
      build(body, sheet) {
        let role = u.role;
        let disabled = u.disabled;
        const name = h('input', { class: 'input', value: u.display_name, required: true });
        const err = h('p', { class: 'form-error', role: 'alert' });
        const save = h('button', { class: 'btn primary wide', type: 'submit' }, 'บันทึก');
        const rf = roleField(role, (v) => { role = v; });
        const dis = switchRow('ปิดการใช้งานบัญชี', disabled, (e) => { disabled = e.target.checked; }, 'เข้าสู่ระบบไม่ได้ และอุปกรณ์ที่ใช้อยู่จะถูกออกจากระบบ');
        if (self) {
          rf.seg.querySelectorAll('button').forEach((b) => { b.disabled = true; });
          dis.querySelector('input').disabled = true;
        }
        const replace = (nu) => { users = users.map((x) => (x.id === nu.id ? nu : x)); draw(); };
        body.append(h('p', { class: 'muted', style: { marginBottom: '14px' } }, `@${u.username}`, u.last_login_at ? `, เข้าใช้ล่าสุด ${fmtRel(u.last_login_at)}` : ', ยังไม่เคยเข้าใช้'),
          ...(self ? [h('div', { class: 'note' }, icon('info'), h('span', {}, 'นี่คือบัญชีของคุณ แก้บทบาทหรือปิดบัญชีตัวเองไม่ได้'))] : []),
          h('form', {
            onsubmit: async (e) => {
              e.preventDefault();
              err.textContent = '';
              const patch = {};
              if (name.value.trim() !== u.display_name) patch.display_name = name.value.trim();
              if (role !== u.role) patch.role = role;
              if (disabled !== u.disabled) patch.disabled = disabled;
              if (!Object.keys(patch).length) { sheet.close(); return; }
              await busy(save, async () => {
                try { const nu = await ctx.api(`/users/${u.id}`, { method: 'PATCH', body: patch }); replace(nu); sheet.close(); ctx.toast('บันทึกแล้ว', 'ok'); } catch (e2) { err.textContent = thaiError(e2, ctx.user, { 409: LAST_ADMIN }); }
              });
            },
          }, field('ชื่อที่แสดง', name), rf.el, dis, err, save));

        // reset password
        const pw = h('input', { class: 'input', type: 'password', minLength: 8, autocomplete: 'new-password' });
        const pwErr = h('p', { class: 'form-error', role: 'alert' });
        const pwBtn = h('button', { class: 'btn wide', type: 'submit' }, icon('key', 'sm'), 'ตั้งรหัสผ่านใหม่');
        body.append(h('div', { class: 'divider' }), h('form', {
          onsubmit: async (e) => {
            e.preventDefault();
            pwErr.textContent = '';
            if (pw.value.length < 8) { pwErr.textContent = 'รหัสผ่านต้องยาวอย่างน้อย 8 ตัวอักษร'; return pw.focus(); }
            await busy(pwBtn, async () => {
              try { await ctx.api(`/users/${u.id}`, { method: 'PATCH', body: { password: pw.value } }); pw.value = ''; ctx.toast(`ตั้งรหัสผ่านใหม่ให้ ${u.display_name} แล้ว`, 'ok'); } catch (e2) { pwErr.textContent = thaiError(e2, ctx.user); }
            });
          },
        }, field('รหัสผ่านใหม่', pw, `${u.display_name} จะถูกออกจากระบบทุกอุปกรณ์ และต้องใช้รหัสใหม่นี้`), pwErr, pwBtn));

        if (!self) {
          const del = h('button', {
            class: 'btn wide', type: 'button', style: { color: 'var(--danger)', marginTop: '8px' },
            onclick: () => inlineConfirm(del, {
              text: `ลบ ${u.display_name} ถาวร? ประวัติการใช้งานยังเก็บไว้ แต่บัญชีนี้จะเข้าสู่ระบบไม่ได้อีก`, confirmLabel: 'ลบสมาชิก',
              onConfirm: async () => {
                try { await ctx.api(`/users/${u.id}`, { method: 'DELETE' }); } catch (e) { ctx.fail(e, { 409: LAST_ADMIN }); throw e; }
                users = users.filter((x) => x.id !== u.id); draw(); sheet.close(); ctx.toast(`ลบ ${u.display_name} แล้ว`, 'ok');
              },
            }),
          }, icon('trash', 'sm'), 'ลบสมาชิก');
          body.append(h('div', { class: 'divider' }), del);
        }
      },
    });
  }

  load();
  return { node };
}
